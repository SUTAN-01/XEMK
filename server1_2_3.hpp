#include <iostream>
#include <memory>
#include <random>
#include <set>
#include <unordered_map>
#include <unordered_set>
#include <thread>
#include <mutex>
#include <chrono>
#include <vector>
#include <string>
#include <atomic>
#include <algorithm> 
#include <websocketpp/config/asio_no_tls.hpp>
#include <websocketpp/server.hpp>
#include <nlohmann/json.hpp>
#include "card.hpp"

using namespace std::chrono_literals;
using json = nlohmann::json;
using std::placeholders::_1;
using std::placeholders::_2;

typedef websocketpp::server<websocketpp::config::asio> server;



// 自定义日志函数替代ROS的日志
class Logger {
public:
    static void info(const std::string& message) {
        std::cout << "[INFO] " << message << std::endl;
    }
    
    static void error(const std::string& message) {
        std::cout << "[ERROR] " << message << std::endl;
    }
};

// 替代ROS发布器的简单类
class SimplePublisher {
public:
    void publish(const std::string& message, const std::string& topic) {
        Logger::info("Published to " + topic + ": " + message);
    }
};



//12.10基本完善，并且不打出卡牌直接点击“打出卡牌默认跳过”，去掉了鸽子防止占用栏位
//后续需要考虑在指定栏位打出牌并传给对手对应卡片的放置栏位，此外需要考虑松鼠和造物的选择问题
//12.10game_interface1_2_3.html
class GameServer {
public:
    int flag = 0;//0开局标志
    int js = 0;
    
    std::random_device rd;
    std::mt19937 gen;
    std::uniform_int_distribution<> dis;

    std::string last_player;

    CardRandomizer cardRandomizer;
    GameServer() : gen(rd()), dis(0, 1), last_player((dis(gen) == 0) ? "player1" : "player2")  {
        // WebSocket服务器设置
        ws_server_.init_asio();
        ws_server_.set_open_handler(bind(&GameServer::on_open, this, ::_1));
        ws_server_.set_close_handler(bind(&GameServer::on_close, this, ::_1));
        ws_server_.set_message_handler(bind(&GameServer::on_message, this, ::_1, ::_2));
        
        ws_server_.listen(8002);
        ws_server_.start_accept();
        
        // 在后台线程运行WebSocket服务器
        ws_thread_ = std::thread([this]() {
            ws_server_.run();
        });
        
        // 游戏状态定时器
        game_timer_thread_ = std::thread([this]() {
            while (running_) {
                update_game_state();
                std::this_thread::sleep_for(100ms);
            }
        });
        
        Logger::info("Game server started on port 8002");
    }
    
    ~GameServer() {
        running_ = false;
        ws_server_.stop();
        
        if (ws_thread_.joinable()) {
            ws_thread_.join();
        }
        
        if (game_timer_thread_.joinable()) {
            game_timer_thread_.join();
        }
    }
private:
    std::string get_connection_info(websocketpp::connection_hdl hdl, server& server) {
    server::connection_ptr con = server.get_con_from_hdl(hdl);
    if (!con) return "Invalid connection";
    
    std::ostringstream info;
    info << "IP: " << con->get_remote_endpoint()
         << ", Resource: " << con->get_resource()
         << ", Host: " << con->get_host();
    
    // 检查是否有查询参数
    std::string query = con->get_uri()->get_query();
    if (!query.empty()) {
        info << ", Query: " << query;
    }
    
    return info.str();
}
    void on_open(websocketpp::connection_hdl hdl) {
        std::lock_guard<std::mutex> lock(connections_mutex_);
        connections_.insert(hdl);
        Logger::info("New client connected");

        std::string info = get_connection_info(hdl, ws_server_);
        Logger::info("New client connected - " + info);
    }
    
    void on_close(websocketpp::connection_hdl hdl) {
        std::lock_guard<std::mutex> lock(connections_mutex_);
        connections_.erase(hdl);
        
        // 检查是否是已注册的玩家断开连接
        std::lock_guard<std::mutex> game_lock(game_mutex_);
        std::string disconnected_player;
        for (const auto& [player_id, player_hdl] : player_connections_) {
            if (player_hdl.lock() == hdl.lock()) {
                disconnected_player = player_id;
                break;
            }
        }
        
        if (!disconnected_player.empty()) {
            // 标记玩家为断开状态，但不移除游戏数据
            disconnected_players_.insert(disconnected_player);
            Logger::info("Player " + disconnected_player + " disconnected");
            
            // 通知另一个玩家
            notify_player_disconnected(disconnected_player);
        }
        
        Logger::info("Client disconnected");
    }
    
    void on_message(websocketpp::connection_hdl hdl, server::message_ptr msg) {
        try {
            auto payload = json::parse(msg->get_payload());
            std::string type = payload["type"];

            
            if (type == "player_join") {
                handle_player_join(hdl, payload);
            } else if (type == "player_action") {
                handle_player_action(hdl, payload);
            } else if (type == "start_new_round") {
                handle_start_new_round(hdl, payload);
            } 
            if(flag == 2)//玩家2开始
            {   
                flag=1;
                std::string player_idnex = payload["player_id"];

                
                if(player_idnex=="player1")  player_idnex="player2";
                else player_idnex="player1";
                // 分配新数字
                check_game_end(player_idnex);
                 // 立即发送当前游戏状态
                send_cards_to_player(player_idnex);
                broadcast_game_state();
                
                // // 通知另一个玩家
                // notify_player_reconnected(player_idnex);
            }
                
            
        } catch (const std::exception& e) {
            Logger::error("Error processing message: " + std::string(e.what()));
        }
    }
    void send_to_connection(websocketpp::connection_hdl hdl, const std::string& message) {
    try {
        ws_server_.send(hdl, message, websocketpp::frame::opcode::text);
    } catch (const websocketpp::exception& e) {
        Logger::error("WebSocket send error: " + std::string(e.what()));
    }
}
   void handle_player_join(websocketpp::connection_hdl hdl, const json& data) {
        std::string player_id = data["player_id"];
        
        std::lock_guard<std::mutex> lock(game_mutex_);
        
        // 检查是否是重新连接
        bool is_reconnect = (player_connections_.find(player_id) != player_connections_.end()) || 
                           (disconnected_players_.find(player_id) != disconnected_players_.end());
        
        if (is_reconnect) {
            // 重新连接处理
            Logger::info("Player " + player_id + " reconnected");
            
            // 更新连接句柄
            player_connections_[player_id] = hdl;
            
            // 从断开列表中移除
            disconnected_players_.erase(player_id);
            
            // 立即发送当前游戏状态
            send_cards_to_player(player_id);
            broadcast_game_state();
            
            // 通知另一个玩家
            notify_player_reconnected(player_id);
            
        } else if (player_connections_.size() < 2) {
            // 新玩家加入
            player_connections_[player_id] = hdl;
            Logger::info("Player " + player_id + " joined the game");
            
         
            
            // 如果两个玩家都加入了，开始游戏
            if (player_connections_.size() == 2) {
                generate_unique_numbers();
                // 发送数字给玩家
                for(auto& [id, hdl] : player_connections_)
                {
                    send_cards_to_player(id);
                }
                    
                broadcast_game_start();
            }
            
        } else {
            // 游戏已满，发送错误消息
            json error_response;
            error_response["type"] = "game_full";
            error_response["message"] = "Game is full, cannot join";
            send_to_connection(hdl, error_response.dump());
        }
    }


    // void handle_player_skip(websocketpp::connection_hdl hdl, const json& data) {
    //     std::string player_id = data["player_id"];
        
    //     std::lock_guard<std::mutex> lock(game_mutex_);
        
    //     // 验证玩家是否已连接
    //     if (player_connections_.find(player_id) == player_connections_.end()) {
    //         Logger::error("Player " + player_id + " not connected");
    //         return;
    //     }
        
    //     // 记录跳过操作
    //     Logger::info("Player " + player_id + " skipped their turn");
        
    //     // 更新最后操作的玩家
    //     last_player = player_id;
        
    //     // 发送跳过接受响应给当前玩家
    //     json accept_response;
    //     accept_response["type"] = "skip_accepted";
    //     accept_response["message"] = "You have skipped your turn";
    //     accept_response["player_id"] = player_id;
    //     send_to_player(player_id, accept_response.dump());
        
    //     // 通知对手该玩家跳过了
    //     std::string opponent_id = (player_id == "player1") ? "player2" : "player1";
    //     if (player_connections_.find(opponent_id) != player_connections_.end()) {
    //         json opponent_response;
    //         opponent_response["type"] = "opponent_skipped";
    //         opponent_response["message"] = player_id + " skipped their turn";
    //         opponent_response["player_id"] = player_id;
    //         send_to_player(opponent_id, opponent_response.dump());
    //     }
        
    //     // 广播游戏状态更新
    //     broadcast_game_state();
        
    //     // 记录到日志
    //     Logger::info("Turn passed to next player after skip by " + player_id);
    // }
    void handle_player_action(websocketpp::connection_hdl hdl, const json& data) {
        flag = 1;
        
        std::string player_id = data["player_id"];
        if (player_id == last_player) {
            Logger::info("received same player's action");
            return;
        } else {
            flag = 2;
        }
        
        // 解析卡牌名称数组
        std::vector<std::string> card_names;
        if (data.contains("cards") && data["cards"].is_array()) {
            for (const auto& name : data["cards"]) {
                if (name.is_string()) {
                    card_names.push_back(name.get<std::string>());
                }
            }
        }
        
        // 通过名称查找卡牌对象
        std::vector<Card*> played_cards;
        // CardRandomizer cardRandomizer; // 假设有全局或可访问的卡牌管理器
        
        for (const auto& name : card_names) {
            Card* card = cardRandomizer.getcard(name);
            if (card) {
                played_cards.push_back(card);
            } else {
                Logger::error("Card not found: " + name);
            }
        }

        // std::vector<Card*> played_cards = data["cards"];///////////////////
        
        std::lock_guard<std::mutex> lock(game_mutex_);
        
        // 验证玩家是否已连接
        if (player_connections_.find(player_id) == player_connections_.end()) {
            Logger::error("Player " + player_id + " not connected");
            return;
        }
        // if(data["func"]!="skip")
        // {
            // 处理玩家出牌逻辑
            process_player_move(player_id, played_cards);
        // }
        

        // // 检查游戏是否结束
        // check_game_end();
        
        
        // 广播游戏状态更新
        broadcast_game_state();

        // 通知对方玩家
        notify_opponent_move(player_id, played_cards);
        
        last_player = player_id;
    }

    void notify_opponent_move(const std::string& player_id, const std::vector<Card*>& cards) {
        // 找到对方玩家的ID
        std::string opponent_id;
        for (const auto& [id, hdl] : player_connections_) {
            if (id != player_id) {
                opponent_id = id;
                // Logger::info("Notified11111111111111111111 " + opponent_id );
                break;
            }
        }
        
        if (!opponent_id.empty()) {
            json opponent_response;
            opponent_response["type"] = "opponent_move";
            
            // 将卡牌指针向量转换为名称数组
            json card_names = json::array();
            for (Card* card : cards) {
                if (card) {
                    card_names.push_back(card->toJson());
                    // card_names.push_back(card->getName());
                }
            }
            opponent_response["cards_played"] = card_names;  // 现在可以赋值了

            // opponent_response["numbers_played"] = numbers;
            opponent_response["player_id"] = player_id;
            
            send_to_player(opponent_id, opponent_response.dump());
            Logger::info("Notified " + opponent_id + " about " + player_id + "'s move");
        }
    }

    void notify_player_disconnected(const std::string& player_id) {
        // 通知另一个玩家有玩家断开连接
        std::string opponent_id;
        for (const auto& [id, hdl] : player_connections_) {
            if (id != player_id && disconnected_players_.find(id) == disconnected_players_.end()) {
                opponent_id = id;
                break;
            }
        }
        
        if (!opponent_id.empty()) {
            json disconnect_response;
            disconnect_response["type"] = "opponent_disconnected";
            disconnect_response["message"] = player_id + " has disconnected";
            disconnect_response["player_id"] = player_id;
            
            send_to_player(opponent_id, disconnect_response.dump());
            Logger::info("Notified " + opponent_id + " about " + player_id + " disconnection");
        }
    }
    
    void notify_player_reconnected(const std::string& player_id) {
        // 通知另一个玩家有玩家重新连接
        std::string opponent_id;
        for (const auto& [id, hdl] : player_connections_) {
            if (id != player_id) {
                opponent_id = id;
                break;
            }
        }
        
        if (!opponent_id.empty()) {
            json reconnect_response;
            reconnect_response["type"] = "opponent_reconnected";
            reconnect_response["message"] = player_id + " has reconnected";
            reconnect_response["player_id"] = player_id;
            
            send_to_player(opponent_id, reconnect_response.dump());
            Logger::info("Notified " + opponent_id + " about " + player_id + " reconnection");
        }
    }

    void handle_start_new_round(websocketpp::connection_hdl hdl, const json& data) {
        std::string player_id = data["player_id"];
        
        std::lock_guard<std::mutex> lock(game_mutex_);
        
        // 检查是否两个玩家都请求了新回合
        static std::set<std::string> new_round_requests;
        new_round_requests.insert(player_id);
        
        if (new_round_requests.size() == 2) {
            // 两个玩家都请求了，开始新回合
            flag = 0;
            new_round_requests.clear();
            
            // 重置游戏状态
            reset_game();
            
            // 重新生成数字并分配给玩家
            generate_unique_numbers();
            
            Logger::info("New round started by both players");
            // 发送新数字给所有玩家
            for (auto& [pid, player_hdl] : player_connections_) {
                Logger::info("New round started by both players "+player_id);
                send_cards_to_player(pid);
            }
            
            broadcast_game_start();
            Logger::info("New round started by both players");
        } else {
            // 只有一个玩家请求，等待另一个
            Logger::info("Player " + player_id + " requested new round, waiting for other player");
            
            // 通知玩家等待另一个玩家
            json wait_response;
            wait_response["type"] = "waiting_for_opponent";
            wait_response["message"] = "Waiting for other player to confirm new round";
            send_to_player(player_id, wait_response.dump());
        }
    }
    
    void generate_unique_numbers(std::string player_id="") {
        
        // std::random_device rd;
        // std::mt19937 gen(rd());
        // std::uniform_int_distribution<> dis(1, 100);
        
        if (flag == 0) {    
            // 清空现有数字
            player_cards_["player1"].clear();
            player_cards_["player2"].clear();
            played_cards_.clear();
            // 初始回合：分配固定数字
            player_cards_["player1"].push_back(cardRandomizer.getcard("松鼠"));
            player_cards_["player2"].push_back(cardRandomizer.getcard("松鼠"));

            // player_cards_["player1"].push_back(cardRandomizer.getskip("鸽子"));
            // player_cards_["player2"].push_back(cardRandomizer.getskip("鸽子"));

            // 生成6个随机数字并平均分配
            std::unordered_multiset<Card*> all_numbers;
            while (all_numbers.size() < 6) {
                all_numbers.insert(cardRandomizer.getRandomCard());
            }
            
            auto it = all_numbers.begin();
            for (int i = 0; i < 6; ++i) {
                if (i % 2 == 0) 
                    player_cards_["player1"].push_back(*it);
                else 
                    player_cards_["player2"].push_back(*it);
                ++it;
            }
        } else {
            // std::string player_id = data["player_id"];
            // 后续回合：每个玩家获得一个新数字
            player_cards_[player_id].push_back(cardRandomizer.getRandomCard());
            // player_numbers_["player2"].insert(dis(gen));
        }
        
        Logger::info("Generated numbers for both players");
    }
    
    void send_cards_to_player(const std::string& player_id) {
        json response;
        response["type"] = "numbers_assigned";
        if(player_cards_.find(player_id)!=player_cards_.end()){
            json card_info = json::array();
            for(auto &card:player_cards_[player_id]){
                if(card){
                    card_info.push_back(card->toJson());
                }
            }
            response["cards"] = card_info;
        }
        // response["numbers"] = player_numbers_[player_id];
        
         Logger::info("send_to_player h players");
        send_to_player(player_id, response.dump());
    }
    
    void process_player_move(const std::string& player_id, const std::vector<Card*>& cards) {
        // int skip1 = 0;
        // 验证玩家是否有所出的数字（考虑重复）
        std::unordered_map<Card*, int> requested_count;
        for (auto card : cards) {
            requested_count[card]++;
        }
        
        // for (const auto& [card, count] : requested_count) {
        //     if (card->getName() == "鸽子") {
        //         // 发送数字更新
        //         send_cards_to_player(player_id);
        //         return;
        //     }
        // }

        // if (skip1 == 0) {
        for (auto card : cards) {
            // if (card->getName() != "鸽子") {
                // 找到并删除一个匹配的元素
                auto it = std::find(player_cards_[player_id].begin(), player_cards_[player_id].end(), card);
                if (it != player_cards_[player_id].end()) {
                    player_cards_[player_id].erase(it);
                    played_cards_.insert(card);
                }
            // }
        }
        // }
         
        // 记录玩家操作
        std::string move_desc = player_id + " played: ";
        std::unordered_map<Card*, int> played_count;
        for (auto card : cards) {
            played_count[card]++;
        }
        
        bool first = true;
        for (const auto& [card, count] : played_count) {
            if (!first) move_desc += ", ";
            move_desc += card->getName();
            if (count > 1) {
                move_desc += "(x" + std::to_string(count) + ")";
            }
            first = false;
        }
        
        // 记录剩余数字
        std::string move_desc1 = player_id + " have: ";
        std::unordered_map<Card *, int> remaining_count;
        for (auto &card : player_cards_[player_id]) {
            remaining_count[card]++;
        }
        
        first = true;
        for (const auto& [card, count] : remaining_count) {
            if (!first) move_desc1 += ", ";
            move_desc1 += card->getName();
            if (count > 1) {
                move_desc1 += "(x" + std::to_string(count) + ")";
            }
            first = false;
        }

        // 发送数字更新
        send_cards_to_player(player_id);
        
        Logger::info(move_desc + move_desc1);
        
        // 发送移动接受消息
        json accept_response;
        accept_response["type"] = "move_accepted";
        accept_response["message"] = move_desc;

        
        json card_info = json::array();
        for(auto &card:cards){
            if(card){
                card_info.push_back(card->toJson());
            }
        }
        accept_response["cards_played"] = card_info;


        // // 将卡牌指针向量转换为名称数组
        // std::vector<std::string> card_names;
        // for (Card* card : cards) {
        //     if (card) {
        //         card_names.push_back(card->getName());
        //     }
        // }
        // accept_response["cards_played"] = card_names;  // 现在可以赋值了
        send_to_player(player_id, accept_response.dump());
        
        // 使用简单的发布器替代ROS发布器
        if (player_id == "player1") {
            player1_pub_.publish(move_desc + " " + move_desc1, "player1_commands");
        } else {
            player2_pub_.publish(move_desc + " " + move_desc1, "player2_commands");
        }
    }
    
    void broadcast_game_start() {
        json response;
        response["type"] = "game_start";
        response["message"] = "Both players joined! Game starting...";
        response["last_player"] = last_player;
        
        broadcast(response.dump());
        Logger::info("Game started with both players");
    }
    
    void broadcast_game_state() {
        std::cout << "[DEBUG] Player1 cards count: " << player_cards_["player1"].size() << std::endl;
        std::cout << "[DEBUG] Player2 cards count: " << player_cards_["player2"].size() << std::endl;
        
        // // 检查每个玩家的卡牌
        // for (auto& card : player_cards_["player1"]) {
        //     if (card) {
        //         std::cout << "[DEBUG] Player1 card: " << card->getName() << std::endl;
        //     }
        // }
        json response;
        response["type"] = "game_state";
        
        // 玩家1状态
        response["player1"]["cards_remaining"] = player_cards_["player1"].size();
        if(player_cards_.find("player1")!=player_cards_.end()){
            json card_info = json::array();
            for(auto &card:player_cards_["player1"]){
                if(card){
                    card_info.push_back(card->toJson());
                }
            }
            response["player1"]["cards"] = card_info;
        }
        // response["player1"]["cards"] = player_cards_["player1"];
        
        // 玩家2状态
        response["player2"]["cards_remaining"] = player_cards_["player2"].size();
        if(player_cards_.find("player2")!=player_cards_.end()){
            json card_info = json::array();
            for(auto &card:player_cards_["player2"]){
                if(card){
                    card_info.push_back(card->toJson());
                }
            }
            response["player2"]["cards"] = card_info;
        }
        
        // response["played_numbers"] = played_cards_;
        
        broadcast(response.dump());
    }
    
    void check_game_end(std::string player_id) {
        // if (flag == 2) {
            generate_unique_numbers(player_id);
        // }
    }
    
    void reset_game() {
        played_cards_.clear();
        played_cards_.clear();
    }
    
    void update_game_state() {
        // 定期更新游戏状态
        std::lock_guard<std::mutex> lock(game_mutex_);
        if (player_connections_.size() > 0) {
            broadcast_game_state();
        }
    }
    
    void send_to_player(const std::string& player_id, const std::string& message) {
        auto it = player_connections_.find(player_id);
        if (it != player_connections_.end()) {
            auto hdl = it->second;
            try {
                ws_server_.send(hdl, message, websocketpp::frame::opcode::text);
            } catch (const websocketpp::exception& e) {
                Logger::error("WebSocket send error: " + std::string(e.what()));
            }
        }
    }
    
    void broadcast(const std::string& message) {
        std::lock_guard<std::mutex> lock(connections_mutex_);
        for (auto hdl : connections_) {
            try {
                ws_server_.send(hdl, message, websocketpp::frame::opcode::text);
            } catch (const websocketpp::exception& e) {
                Logger::error("WebSocket broadcast error: " + std::string(e.what()));
            }
        }
    }

private:
   // WebSocket服务器
    server ws_server_;
    std::thread ws_thread_;
    std::set<websocketpp::connection_hdl, std::owner_less<websocketpp::connection_hdl>> connections_;
    std::mutex connections_mutex_;
    
    // 游戏状态
    // std::unordered_map<std::string, std::unordered_multiset<int>> player_numbers_;
    std::unordered_map<std::string, std::vector<Card*>> player_cards_;

    std::unordered_map<std::string, websocketpp::connection_hdl> player_connections_;
    std::set<std::string> disconnected_players_; // 新增：存储断开连接的玩家

    // std::set<int> played_numbers_;
    std::unordered_multiset<Card*> played_cards_;

    std::mutex game_mutex_;
    
    // 替代ROS发布器
    SimplePublisher player1_pub_;
    SimplePublisher player2_pub_;
    
    // 定时器控制
    std::thread game_timer_thread_;
    std::atomic<bool> running_{true};
};