#ifndef PLAY_HPP
#define PLAY_HPP
#include "card1.hpp"

using namespace std::chrono_literals;
using json = nlohmann::json;
using std::placeholders::_1;
using std::placeholders::_2;

//1212部分为旧但有出新的卡牌时，会在手牌中额外扣除重复的手牌
class play{ 

public:
    // play();
    //记录当前玩家出的牌
    std::vector<Card*> cur_play(std::string player_id, std::vector<std::vector<Card*>> &cur_slots_cards,
        std::vector<std::string> card_names,CardRandomizer &cardRandomizer,int card_id){
        played_cards.clear();
        cur_player_slots_cards[player_id]=cur_slots_cards;
        
        if(last_slots_cards[player_id]!=cur_player_slots_cards[player_id])
        {
            last_slots_cards[player_id]=cur_player_slots_cards[player_id];
            played_cards=played_cards_update(card_names, cardRandomizer,card_id);//加上了不该加的
        }
        return played_cards;
    }
    int getHP(int HP){
        return character_HP+HP;
    }

    std::vector<Card*> played_cards_update(std::vector<std::string> card_names, CardRandomizer &cardRandomizer,int card_id){
        // 通过名称查找卡牌对象
        for (const auto& name : card_names) {
            if(name=="松鼠") {
                Card* card = cardRandomizer.getsquirrel();
                // if(card->get_play_current_card_id()==true)
                // {
                    // card->set_play_current_card_id(iniflag++);
                    played_cards.push_back(card);
                // }
                
            }
            else {
                Card* card = cardRandomizer.getcard(name,1);
                // if(card->get_play_current_card_id()==true){
                    // card->set_play_current_card_id(iniflag++);
                    played_cards.push_back(card);
                // }
                
            }
        }
        return played_cards;
    }

private:
    int iniflag=0;
    int character_HP=0;
    std::vector<Card*> played_cards={};
    std::unordered_map<std::string, std::vector<std::vector<Card*>>> cur_player_slots_cards;
    std::unordered_map<std::string, std::vector<std::vector<Card*>>> last_slots_cards;
};

#endif