
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
#include "card3_2_3.hpp"
#include "play3_2_3.hpp"

using namespace std::chrono_literals;
using json = nlohmann::json;
using std::placeholders::_1;
using std::placeholders::_2;

typedef websocketpp::server<websocketpp::config::asio> server;

//初步实现功能，需要完善显示界面

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



// 数字实现基本功能game_interface1_4_1
//12.2当前第一个连接的玩家如果先出第一张牌，则对方玩家不显示第一个玩家的第一张牌的内容?
//12.3基本完善，后续需要考虑将某数字指定放在某个区域，直到需要删除
//12.12似乎当前回合中的牌只要在场上，己方回合结束后都会在手牌中反复扣除
//12.13有新出牌的情况下，若场上有原有的牌，该牌会在手牌中被反复扣除，需要考虑为每张牌进行唯一编号，并且编号不能在内存中被同步修改,
//12.13现在是去不掉卡牌了，由于出的卡牌id编号可能在0到当前的任意范围内，需要考虑当前played_cards_update中准确找到本次出的牌的id编号进行删除
//12.17目前基本对战功能已具备，但己方出的牌在栏位上之后不会有任何更改，无法根据实际掉血或退场，但在对方栏能正常显示
//12.18目前已经有了正常的对战逻辑，同时场上的双方卡片信息会随时更新，只是血量为0的己方卡牌需要手动删除，除非该卡槽本回合不需要放卡，
//      但是目前缺少卡牌献祭规则和死后的骨头掉落，同时缺少玩家血量、卡牌先后手的提示，目前默认先出牌的玩家卡牌先攻击
//      handle_player_action中需要补充玩家选择献祭场上卡牌的逻辑
class GameServer {
public:
    int flag = 0;//0开局标志
    int choosing_card = 0;
    std::string player_idnex_op="";
    std::string player_idnex="";
    
    // int last_slots_cards_flg=0;
    int card_id=0;
    int fist=0;
    
    std::random_device rd;
    std::mt19937 gen;
    std::uniform_int_distribution<> dis;

    std::string last_player;

    CardRandomizer cardRandomizer;
    play game_play;
    GameServer() : gen(rd()), dis(0, 1), last_player((dis(gen) == 0) ? "player1" : "player2") , slots_cards(4) {
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
            
            player_idnex = payload["player_id"];

            if(player_idnex=="player1")  player_idnex_op="player2";
            else player_idnex_op="player1";
            //card_placement_update
            
            // if(flag==1&&last_slots_cards[player_idnex].size()!=0){
            //     slots_cards=last_slots_cards[player_idnex];
            //     player_bones=last_player_bones;
            // }else if(flag==2&&cur_player_slots_cards[player_idnex].size()!=0){//第二个玩家
            //     slots_cards=cur_player_slots_cards[player_idnex];
            //     player_bones=cur_player_bones;
            // }
            
            // if(choosing_card==1&&type=="special_action"&&flag>0)
            if(choosing_card==1&&type=="special_action")
            {
                std::string action_type = payload["action_type"];
                generate_unique_numbers(player_idnex, action_type);
                if(flag==2) flag=0;

                // 立即发送新卡牌
                send_cards_to_player(player_idnex);
                
                choosing_card=0;
            }else if(choosing_card==0){
                if (type == "player_join") {
                    handle_player_join(hdl, payload);
                } else if (type == "card_placement_update") {//收到场上卡牌更新消息
                    if(player_idnex!=last_player){
                        //payload["action"]有"clear"和"add"两种，需要一个总的计数xianjiing，"clear"-1,"add"+1
                        //同时当"add"的卡牌需要献祭时，需要确保总的计数最终为原计数-血滴数
                        int xj_card_id=payload["card"]["card_id"];
                        if(payload["action"]=="clear"){
                            for(auto &&it=player_cards_[player_idnex].begin();it!=player_cards_[player_idnex].end();it++){
                                if((*it)->get_play_current_card_id()==xj_card_id){
                                    if((*it)->get_card_state()==1){
                                        xianjiing+=1;

                                        if(flag==0){//第一个玩家回合结束前
                                            last_player_bones+=1;
                                            // slots_cards=last_slots_cards[player_idnex];
                                        }else if(flag==1){//第二个玩家回合结束前
                                            cur_player_bones+=1;
                                            // slots_cards=cur_player_slots_cards[player_idnex];
                                        }

                                        //将去掉的牌从手牌中删除
                                        for(auto &&it=player_cards_[player_idnex].begin();it!=player_cards_[player_idnex].end();it++){
                                            int id=(*it)->get_play_current_card_id();
                                            if((*it)->get_play_current_card_id()==xj_card_id){
                                                (*it)->set_card_state(0);
                                                it=player_cards_[player_idnex].erase(it);
                                                
                                            }
                                        }
                                        if(flag==0){//第一个玩家回合结束前
                                           
                                            process_player_move(player_idnex, last_slots_cards[player_idnex]);
                                        }else if(flag==1){//第二个玩家回合结束前
                                           
                                            process_player_move(player_idnex, cur_player_slots_cards[player_idnex]);
                                        }
                                        break;
                                    }else{
                                        break;
                                    }
                                    
                                }
                            }
                            
                        } else if(payload["action"]=="add"){
                            // xianjiing+=1;
                            if(payload["card"]["cost"].size()>0){
                                // std::string cost = payload["card"]["cost"];
                                std::string resource = payload["card"]["cost"][0]["resource"];
                                if(resource=="血滴"){
                                    int cost_num=payload["card"]["cost"][0]["amount"];
                                    if(xianjiing>=cost_num){
                                        for(auto &&it=player_cards_[player_idnex].begin();it!=player_cards_[player_idnex].end();it++){
                                            if((*it)->get_play_current_card_id()==xj_card_id){
                                                (*it)->set_card_state(1);
                                                break;
                                            }
                                        }
                                    }
                                }
                            }else{
                                for(auto &&it=player_cards_[player_idnex].begin();it!=player_cards_[player_idnex].end();it++){
                                    if((*it)->get_play_current_card_id()==xj_card_id){
                                        (*it)->set_card_state(1);
                                        break;
                                    }
                                }
                            }
                        }
                        //将当前玩家的骨头数量发给前端
                    }
                }
                else if(type == "player_action") {
                    std::string player_id = player_idnex;
                    if (player_id == last_player) {
                        Logger::info("received same player's action");
                        // return;
                    } else {
                        flag+=1;
                        //需要补充玩家出的牌是否满足条件，即注意花费
                        std::vector<std::vector<Card*>> slots_cards=handle_player_action(hdl, payload);   
                        xianjiing=0;      
                    }
                    
                } else if (type == "start_new_round") {
                    handle_start_new_round(hdl, payload);
                }
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

    void send_choose_card_info(std::string player_idnex_op){
            // 发送移动接受消息
            json accept_response;
            accept_response["type"] = "special_action_request";
            send_to_player(player_idnex_op, accept_response.dump());
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

    std::vector<std::vector<Card*>> handle_player_action(websocketpp::connection_hdl hdl, const json& data) {
        
       //玩家首先通过界面拖动卡牌进行出牌，之后会自动统计出牌栏中存在的卡牌信息data["slots"]，本函数通过data["slots"]分析玩家打出了哪些牌，
       //从而更改玩家手牌信息，确保玩家手牌player_cards中不会出现已经打出的牌，但考虑到每次出牌后都需要根据出牌栏的卡牌信息去找到手牌中是否存在该牌，
       //因此上场的牌不能简单的从player_cards中删除，从而让场上的牌存在多个回合，同时有新牌打出时旧牌和新牌能同时在场，
       //只有卡牌HP归零是才要在player_cards中删除，同时需要即刻在场上删除。
        std::lock_guard<std::mutex> lock(game_mutex_);
       //为保证对每张牌的操作不影响其他内容一致的牌，从0开始为每张发放的牌进行id编号，从而保证不会对多张相同的牌进行同时操作。id编号在每次获取牌时分发，
       //其中在CardRandomizer类中给出了卡的模板，玩家每次获取的卡是模板的复制卡
        // int sss=slots_cards.size();//4个槽位
       
        // int in_card_num=0;//手牌可供献祭的的牌数量


        //12.21_14:15如果第一回合就放置多张松鼠牌，之后献祭掉该怎么办?
        //直接看手牌数量和剩余栏位数量，首先将需要献祭的牌放入场上或者选定，之后从player_cards_[player_idnex]中
        //挑选不需要献祭的指定数量的牌，或者场上（状态为1）的牌，此时需要显示出所有可献祭牌，场上的要显示在场上，
        //可供选择的牌数量只有场上所有的牌和手牌中和空栏位相同数量的松鼠牌，献祭掉的牌需要通知对方

        //要上场的卡需要献祭数量x(x<=4),如果场上牌数量=4,直接从场上扣除x张牌
        //如果场上牌数量<4,可以从场上的y张牌和手牌中4-y张松鼠牌中选择x张牌献祭

        //1225或者可以只看场上的卡，也就是献祭前需要把想要献祭的卡打到场上，之后在出需要献祭的卡。
        //这样需要考虑卡到场上后立即被算作场上的牌，而不是等点击结束回合按键后，且任何的卡牌变动最好都能及时通知对方玩家
        if(flag==1&&last_slots_cards[player_idnex].size()!=0){
            slots_cards=last_slots_cards[player_idnex];
            player_bones=last_player_bones;
        }else if(flag==2&&cur_player_slots_cards[player_idnex].size()!=0){//第二个玩家
            slots_cards=cur_player_slots_cards[player_idnex];
            player_bones=cur_player_bones;
        }
        
        //解析玩家出牌
        // anly_slot_card_end=0;
        slots_cards=game_play.an_slot_card(data, player_cards_, cardRandomizer, 
            card_id, player_idnex, player_bones, slots_cards);
        
        if(choosing_card==0)//玩家结束
        {   
            send_choose_card_info(player_idnex_op);//发送对方玩家请求发牌的信息
            int game_end = 0;
            if (flag == 1) {
                // 记录当前玩家的信息
                last_slots_cards[player_idnex] = slots_cards;
                last_player_bones=player_bones;
            }
            else {
                cur_player_bones=player_bones;
                cur_player_slots_cards[player_idnex] = slots_cards;

                //卡牌对战逻辑
                auto slotscards=game_play.cur_plays(cur_player_slots_cards,last_slots_cards, 
                    player_idnex,player_idnex_op,player_cards_,game_end,last_player_bones,cur_player_bones);
                std::vector<std::vector<Card*>> last_player_slots_cards1=slotscards[0];//先出牌玩家
                std::vector<std::vector<Card*>> cur_player_slots_cards1=slotscards[1];
            
                if(game_end==-1){
                    Logger::info(player_idnex_op+"loss the game over!!!!!!!!!!!!!!!");
                }else if(game_end==1){
                    Logger::info(player_idnex+"loss the game over!!!!!!!!!!!!!!!");
                }
            }

            // 验证玩家是否已连接
            if (player_connections_.find(player_idnex_op) == player_connections_.end()) {
                Logger::error("Player " + player_idnex_op + " not connected");
                return slots_cards;
            }

            //通知双方玩家血量、骨头数量变化
            process_player_move(player_idnex_op,last_slots_cards[player_idnex_op]);
            // 通知对方玩家
            notify_opponent_move(player_idnex_op, last_slots_cards[player_idnex_op]);
            choosing_card=1;
        }  
        
        // 验证玩家是否已连接
        if (player_connections_.find(player_idnex) == player_connections_.end()) {
            Logger::error("Player " + player_idnex + " not connected");
            return slots_cards;
        }

        // // 处理玩家出牌逻辑
        process_player_move(player_idnex, slots_cards);
        // send_cards_to_player(player_idnex);

        // 通知对方玩家
        notify_opponent_move(player_idnex, slots_cards);
        // if(anly_slot_card_end==1){
            last_player = player_idnex;
        // }

        return slots_cards;
    }

    void notify_opponent_move(const std::string& player_id, 
        const std::vector<std::vector<Card*>> &slots_cards) {
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
            for (auto &cards : slots_cards) {
                for(auto &card : cards){
                    if(card&&card->get_card_state()==1){
                        //  if(card){
                        card_names.push_back(card->toJson());
                    }else{
                        card_names.push_back(nullptr);
                    }
                }
            }
            opponent_response["cards_played"] = card_names;  // 现在可以赋值了

            json slots_json = json::array();
            for (const auto& slot : slots_cards) {
                json slot_json = json::array();
                for (Card* card : slot) {
                    if (card&&card->get_card_state()!=0&&card->getHP()>0) {
                    //  if(card){
                        slot_json.push_back(card->toJson());  // 使用 toJson() 方法
                    }
                    else{
                        slot_json.push_back(nullptr);
                    }
                }
                slots_json.push_back(slot_json);
            }
            opponent_response["slots"] = slots_json;  // 现在可以赋值了
      
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
    
    void generate_unique_numbers(std::string player_id="", std::string action_type="") {
        
        // std::random_device rd;
        // std::mt19937 gen(rd());
        // std::uniform_int_distribution<> dis(1, 100);
        
        if (flag == 0) {    
            // 清空现有数字
            player_cards_["player1"].clear();
            player_cards_["player2"].clear();
            played_cards_.clear();
            // 初始回合：分配固定数字
            player_cards_["player1"].push_back(cardRandomizer.getsquirrel());
            player_cards_["player2"].push_back(cardRandomizer.getsquirrel());

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
            if(action_type=="creations")
            {
                player_cards_[player_id].push_back(cardRandomizer.getRandomCard());
            }
            else //if(action_type=="squirrels")
            {
                player_cards_[player_id].push_back(cardRandomizer.getsquirrel());
            }
            // std::string player_id = data["player_id"];
            // 后续回合：每个玩家获得一个新数字
            // player_cards_[player_id].push_back(cardRandomizer.getRandomCard());
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
                if(card&&card->get_card_state()==0){//如果card&&card->get_card_state()==0，已经在场上但还存活的手牌因为状态为1,没有被发送给客户端，导致直接丢失
                // if(card){
                    card_json = card->toJson();  // 获取基础JSON
                    // // 添加地址信息
                    // card_json["memory_address"] = reinterpret_cast<uintptr_t>(card);
                    // card_json["is_valid"] = (card != nullptr);
                    card_info.push_back(card_json);
                }
            }
            response["cards"] = card_info;
            
                // card_json["is_valid"] = (card != nullptr);
        }
        // response["numbers"] = player_numbers_[player_id];
        
        //  Logger::info("send_to_player h players");
        send_to_player(player_id, response.dump());
    }
    
    void process_player_move(const std::string& player_id, const std::vector<std::vector<Card*>>& slots_cards) {
        //专门用来更新己方场上的卡牌信息
         
        // 记录玩家操作
        std::string move_desc = player_id + " played: ";
        std::unordered_map<Card*, int> played_count;
        for (auto cards : slots_cards) {
            for(auto card : cards)
            {
                if(card)
                {
                    played_count[card]++;
                }
                
            }
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
        
    

        //上述注释掉的代码若某槽位无卡牌会被自动略过，导致只有有卡牌的信息会被加进card_info，没法关联槽位
        for (auto &cards : slots_cards) {
            // 如果当前栏位有卡牌
            if (!cards.empty()) {
                for(auto &card : cards) {
                    if(card && card->get_card_state()!=0&&card->getHP()>0) {
                        card_info.push_back(card->toJson());
                    } else{
                        card_info.push_back(nullptr);
                    }
                }
            } else {
                // 栏位为空，添加一个null表示空栏位
                card_info.push_back(nullptr);
                // 或者如果要保持每个栏位位置都有占位符：
                // CardRandomizer skipcard;
                // card_info.push_back(skipcard.getskip("鸽子")->toJson());
            }
        }
        
        accept_response["cards_played"] = card_info;

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
    
    
    // void check_game_end(std::string player_id) {
    //         generate_unique_numbers(player_id);
    // }
    
    void reset_game() {
        played_cards_.clear();
        played_cards_.clear();
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

    std::vector<std::vector<Card*>> slots_cards;
    std::unordered_map<std::string, std::vector<std::vector<Card*>>> last_slots_cards;
    std::unordered_map<std::string, std::vector<std::vector<Card*>>> cur_player_slots_cards;

    int last_player_bones=0;
    int cur_player_bones=0;
    int player_bones;
    int anly_slot_card_end=0;
    int xianjiing=0;
    
    // 游戏状态
    // std::unordered_map<std::string, std::unordered_multiset<int>> player_numbers_;
    std::unordered_map<std::string, std::vector<Card*>> player_cards_;

    std::unordered_map<std::string, websocketpp::connection_hdl> player_connections_;
    std::set<std::string> disconnected_players_; // 新增：存储断开连接的玩家

    // std::set<int> played_numbers_;
    std::unordered_multiset<Card*> played_cards_;
    json card_json;

    std::mutex game_mutex_;
    
    // 替代ROS发布器
    SimplePublisher player1_pub_;
    SimplePublisher player2_pub_;
    
    // 定时器控制
    std::thread game_timer_thread_;
    std::atomic<bool> running_{true};

    int character_HP = 0;
};