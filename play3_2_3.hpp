#ifndef PLAY_HPP
#define PLAY_HPP
#include "card3_2_3.hpp"
// #include "server1_3.hpp"

using namespace std::chrono_literals;
using json = nlohmann::json;
using std::placeholders::_1;
using std::placeholders::_2;

//1212部分为旧但有出新的卡牌时，会在手牌中额外扣除重复的手牌
class play{ 

public:
    json send_move(std::vector<std::vector<Card*>> &slots_cards){
        // 发送移动接受消息
        json accept_response;
        accept_response["type"] = "move_accepted";
        // accept_response["message"] = move_desc;

        
        json card_info = json::array();
        for (auto cards : slots_cards) {
            for(auto card : cards)
            {
                if(card)
                {
                    card_info.push_back(card->toJson());
                }
            }
        }
        accept_response["cards_played"] = card_info;
        return accept_response;
    }

    auto cur_plays(std::unordered_map<std::string, std::vector<std::vector<Card*>>> &cur_player_slots_cards,
                    std::unordered_map<std::string, std::vector<std::vector<Card*>>> &last_slots_cards,
                    std::string cur_player_id, std::string op_player_id,
                    std::unordered_map<std::string, std::vector<Card*>> &player_cards_, int &game_end,
                    int &last_player_bones,int &cur_player_bones) {
            // int game_end = 0;
            // 安全检查函数
            auto safe_get_card = [&](const std::string& player_id, int slot_idx, 
                                    std::unordered_map<std::string, std::vector<std::vector<Card*>>>& slots_map) -> Card* {
                // 1. 检查玩家是否存在
                auto player_it = slots_map.find(player_id);
                if (player_it == slots_map.end()) {
                    std::cerr << "Player " << player_id << " not found in slots_map" << std::endl;
                    return nullptr;
                }
                
                // 2. 检查槽位索引
                auto& player_slots = player_it->second;
                if (slot_idx < 0 || slot_idx >= player_slots.size()) {
                    std::cerr << "Slot index " << slot_idx << " out of bounds for player " << player_id 
                            << " (size=" << player_slots.size() << ")" << std::endl;
                    return nullptr;
                }
                
                // 3. 检查槽位内是否有卡牌
                auto& slot = player_slots[slot_idx];
                if (slot.empty()) {
                    return nullptr;  // 空槽位
                }
                
                // 4. 返回第一张卡牌
                return slot[0];
            };
            
            // 对战逻辑
            for (int i = 0; i < 4; i++) {  // 假设最多4个槽位
                // 使用安全函数获取卡牌
                Card* cur_card = safe_get_card(cur_player_id, i, cur_player_slots_cards);
                Card* op_card = safe_get_card(op_player_id, i, last_slots_cards);
                
                // 记录是否有卡牌
                bool cur_has_card = (cur_card != nullptr);
                bool op_has_card = (op_card != nullptr);
                
                // 战斗逻辑
                if (op_has_card) {  // 对方有卡牌
                    if (!cur_has_card) {  // 当前玩家无牌
                        // 当前玩家承担对方卡牌伤害
                        character_HP += op_card->getATK();
                        
                        if (character_HP >= 5) {  // 注意：应该是 >= 5 吗？
                            game_end= 1;  // 当前玩家死亡
                        }
                    } else {  // 双方都有牌
                        cur_card->lossHP(op_card->getATK());
                        if (cur_card->getHP() <= 0) {
                            if (cur_card->getHP() < 0) {
                                character_HP -= cur_card->getHP();  // 注意：这里应该是加还是减？
                                if (character_HP <= -5) {  
                                    game_end= -1;  // 对方玩家死亡
                                }
                            }
                            // 卡牌死亡
                            // cur_card->set_card_state(0);
                            // 注意：这里删除卡牌后，后续访问会出问题
                            // 需要从 cur_player_slots_cards 中移除

                            auto& player_cards = player_cards_[cur_player_id];
                            for (auto it = player_cards.begin(); it != player_cards.end(); ){
                                if (cur_card == *it){
                                    it = player_cards.erase(it);
                                    cur_player_bones+=1;
                                    //骨头🦴+=1
                                    break;
                                }
                                else{
                                    ++it;
                                }
                            }
                            for(auto &slot_cards : cur_player_slots_cards[cur_player_id]){
                                for(auto it = slot_cards.begin();it != slot_cards.end();){
                                    if (cur_card == *it){
                                        it = slot_cards.erase(it);
                                    }
                                    else{
                                        ++it;
                                    }
                                }
                            }

                            // delete cur_card;
                            // cur_player_slots_cards[cur_player_id][i].clear();
                        }
                    }
                } else {  // 对方无牌
                    if (cur_has_card) {  // 当前玩家有牌
                        character_HP -= cur_card->getATK();
                        if (character_HP <= -5) {  // 注意：应该是 <= -5 吗？
                            game_end = -1;  
                        }
                    }
                }
                
                // 第二段逻辑：反向攻击（当前玩家的牌攻击对方的牌）
                // 注意：这里 cur_card 和 op_card 可能已经在上面的逻辑中被修改或删除
                // 需要重新获取
                cur_card = safe_get_card(cur_player_id, i, cur_player_slots_cards);
                op_card = safe_get_card(op_player_id, i, last_slots_cards);
                
                cur_has_card = (cur_card != nullptr);
                op_has_card = (op_card != nullptr);
                
                if (cur_has_card&&game_end!=1) {  // 当前玩家有牌
                    if (op_has_card) {  // 对方有牌
                        if(cur_card->getHP()>0){
                            op_card->lossHP(cur_card->getATK());
                        }
                        
                        if (op_card->getHP() <= 0) {
                            if (op_card->getHP() < 0) {
                                character_HP += op_card->getHP();
                                if (character_HP >= 5) {  // 注意：这里逻辑有问题
                                    game_end= 1;  // 对方玩家死亡
                                }
                            }
                            // 卡牌死亡
                            auto& player_cards = player_cards_[op_player_id];
                            for (auto it = player_cards.begin(); it != player_cards.end(); ){
                                if (op_card == *it){
                                    it = player_cards.erase(it);
                                    //骨头🦴+=1
                                    last_player_bones+=1;
                                    break;
                                }
                                else{
                                    ++it;
                                }
                            }
                            for(auto &slot_cards : last_slots_cards[op_player_id]){
                                for(auto it = slot_cards.begin();it != slot_cards.end();){
                                    if (op_card == *it){
                                        it = slot_cards.erase(it);
                                        break;
                                    }
                                    else{
                                        ++it;
                                    }
                                }
                            }
                           
                        }
                    }
                }
            }
            
            round += 1;
        // 直接使用vector存储两个槽位向量
        std::vector<std::vector<std::vector<Card*>>> players_slots_cards{
            last_slots_cards[op_player_id],  // 对方玩家槽位
            cur_player_slots_cards[cur_player_id]  // 当前玩家槽位
        };
        return players_slots_cards;
        // return game_end;
    }

    //12.29当前"card_placement_update"类型的信息中的"action"给出了add和clear两种，同时发送玩家对应id，
    //但是接收card_placement_update本身需要在on_massage中，同时需要对id进行判断，确保是正确的玩家进行的操作
    std::vector<std::vector<Card*>> an_slot_card(const json& data, std::unordered_map<std::string, std::vector<Card*>> &player_cards_,
        CardRandomizer &cardRandomizer,int &card_id,std::string &player_idnex,int &player_bones,
        std::vector<std::vector<Card*>> &slots_cards){
        // int out_card_num=0;
        int ind=0;
        

        // 解析 slots 数据
        if (data.contains("slots") && data["slots"].is_array()) {
            // 调试输出：打印整个 slots 数据
            // std::cout << "Slots data: " << data["slots"].dump(2) << std::endl;
            
            for (const auto& slot_data : data["slots"]) { // data["slots"]中含有四个slot_data
                std::vector<Card*> slot_cards;
                
                for (const auto& card_data : slot_data) { // slot_data中包含多个card_data
                    card_id = card_data["id"].get<int>();

                    // 在 player_cards_[player_id] 中查找并删除匹配的卡牌
                    auto& player_cards = player_cards_[player_idnex];

                    // 方法: 使用迭代器遍历和删除
                    for (auto it = player_cards.begin(); it != player_cards.end();) {
                        int player_card_id = (*it)->get_play_current_card_id();
                        if (player_card_id == card_id) {
                            auto costit=(*it)->getcost().begin();
                            int state=(*it)->get_card_state();
                            if(costit!=nullptr&&state!=1){//state!=1表示卡牌原本不在场上，用来防止已上场的牌反复扣除资源
                                std::string cost_name=costit->first;
                                int cost_num=costit->second;
                                if(costit->first=="骨头"){
                                    if(player_bones>=costit->second){
                                        //可以出牌
                                        player_bones-=costit->second;

                                        // 直接将找到的卡牌添加到 slot_cards 中
                                        if(slot_cards.empty()){
                                            slot_cards.push_back(*it);
                                            (*it)->set_card_state(1);
                                        }
                                    }
                                }
                            }else{
                                //不再需要献祭或原本就在场上
                                // if((*it)->getHP()<=0){
                                //     it = player_cards.erase(it);
                                //     slot_cards.clear();
                                //     player_bones+=1;
                                // }else{
                                    // 直接将找到的卡牌添加到 slot_cards 中
                                    if(state!=0){
                                        // while(!slot_cards.empty()){
                                        //     auto &card_y=slot_cards.back();
                                        //     for(auto &card:player_cards){
                                        //         if(card_y==card){
                                        //             player_cards.erase(card);
                                        //         }
                                        //     }
                                        //     delete card;
                                        //     slot_cards.pop_back();
                                        // }
                                        slot_cards.push_back(*it);
                                        // (*it)->set_card_state(1);
                                    }
                                    
                                // }
                            }
                            break; // 找到后跳出循环，假设卡牌ID是唯一的
                        } else {
                            // slot_cards.push_back(card_data);
                            ++it;
                        }
                    }
                }
                slots_cards[ind]=(slot_cards);
                ind++;
            }
        }

        return slots_cards;
    }

private:
    int iniflag=0;
    int round=0;
    int character_HP=0;
    int need_num=0;
    // Card* op_cur_card;
    // Card* cur_card;

    // GameServer game_server;
    // int op_character_HP=0;
    std::vector<Card*> played_cards={};

};

#endif