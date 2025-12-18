
#ifndef CARD_HPP
#define CARD_HPP

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
#include <websocketpp/config/asio_no_tls.hpp>
#include <websocketpp/server.hpp>
#include <nlohmann/json.hpp>


//数字实现基本功能game_interface1_2_4  同时解决-1和其他数字被对方看到的问题

class Card{
protected:
    std::string name;//名字
    int HP;//生命
    int ATK;//攻击
    std::string property;//属性
    std::unordered_multimap<std::string,int> cost;
    // std::unordered_mulitset<> cost;//花费
    std::string race;//种族
    // bool play_current=true;
    int card_id=0;
    int card_state=0;
public:
    Card(std::string name,int HP,int ATK,std::string property,std::unordered_multimap<std::string,int> cost,std::string race)
    :name(name),HP(HP),ATK(ATK),property(property),cost(cost),race(race)
    { 

    }

    // 添加复制构造函数
    Card(const Card& other) : 
        name(other.name),
        HP(other.HP),
        ATK(other.ATK),
        property(other.property),
        cost(other.cost),
        race(other.race),
        card_id(0)  // 注意：这里重置 card_id 为 0，不复制原来的 ID
    {}
    
    // 添加赋值运算符
    Card& operator=(const Card& other) {
        if (this != &other) {
            name = other.name;
            HP = other.HP;
            ATK = other.ATK;
            property = other.property;
            cost = other.cost;
            race = other.race;
            card_id = 0;  // 重置 ID
        }
        return *this;
    }
    virtual ~Card()=default;
    virtual void showInfo() const{
        std::cout<<"Name: "<<name.c_str()<<std::endl;
        std::cout<<"HP: "<<HP<<std::endl;
        std::cout<<"ATK: "<<ATK<<std::endl;
        std::cout<<"Property: "<<property<<std::endl;
        std::cout<<"play_current_card_id: "<<card_id<<std::endl;

    }

    // 添加将卡牌转换为JSON的方法
    nlohmann::json toJson() const {
        nlohmann::json cardJson;
        cardJson["name"] = name;
        cardJson["HP"] = HP;
        cardJson["ATK"] = ATK;
        cardJson["property"] = property;
        cardJson["race"] = race;
        cardJson["card_id"] = card_id;
        
        // 将 cost multimap 转换为 JSON 数组
        nlohmann::json costArray = nlohmann::json::array();
        for (const auto& [resource, amount] : cost) {
            nlohmann::json costItem;
            costItem["resource"] = resource;
            costItem["amount"] = amount;
            costArray.push_back(costItem);
        }
        cardJson["cost"] = costArray;
        
        return cardJson;
    }

    void set_card_state(int card_state){
        this->card_state = card_state;
    }

    int get_card_state(){
        return this->card_state;
    }
    std::string getName() const{
        return name;
    }
    std::string getproperty() const{
        return property;
    }
    std::string getrace() const{
        return race;
    }

    std::unordered_multimap<std::string,int> getcost() const{
        return cost;
    }
    int getHP() const{
        return HP;
    }
    int getATK() const{
        return ATK;
    }
    void set_play_current_card_id(int play_current_card_id){
        this->card_id = play_current_card_id;
    }

    int get_play_current_card_id(){
        return this->card_id;
    }
};

class Cardfactory{
public:
    virtual ~Cardfactory()=default;
    virtual std::unique_ptr<Card> createCard(std::string name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race) = 0;
    std::unique_ptr<Card> createCardwithsetup(const std::string &name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race){
        auto card = createCard(name, HP, ATK, property, cost, race);
        setupCard(card.get());
        return card;
    }
    
protected:
    virtual void setupCard(Card* card){
        card->showInfo();
    }
   
};

class canoidea:public Cardfactory{
public:
    virtual std::unique_ptr<Card> createCard(std::string name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race) override{
        return std::make_unique<Card>(name,HP,ATK,property,cost,race);
    }
protected:
    virtual void setupCard(Card* card) {
        Cardfactory::setupCard(card);
        std::cout<<"犬类 Card created: %s", card->getName().c_str();
    }
};


class reptilia:public Cardfactory{
public:
    virtual std::unique_ptr<Card> createCard(std::string name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race) {
        return std::make_unique<Card>(name,HP,ATK,property,cost,race);
    }
protected:
    virtual void setupCard(Card* card) {
        Cardfactory::setupCard(card);
        std::cout<<"爬行类 Card created: %s", card->getName().c_str();
    }
};

class birds:public Cardfactory{
public:
    virtual std::unique_ptr<Card> createCard(std::string name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race) {
        return std::make_unique<Card>(name,HP,ATK,property,cost,race);
    }
protected:
    virtual void setupCard(Card* card) {
        Cardfactory::setupCard(card);
        std::cout<<"鸟类 Card created: %s", card->getName().c_str();
    }
};


class Ungulata:public Cardfactory{
public:
    virtual std::unique_ptr<Card> createCard(std::string name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race) {
        return std::make_unique<Card>(name,HP,ATK,property,cost,race);
    }
protected:
    virtual void setupCard(Card* card) {
        Cardfactory::setupCard(card);
        std::cout<<"有蹄类 Card created: %s", card->getName().c_str();
    }
};


class insecta:public Cardfactory{
public:
    virtual std::unique_ptr<Card> createCard(std::string name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race) {
        return std::make_unique<Card>(name,HP,ATK,property,cost,race);
    }
protected:
    virtual void setupCard(Card* card) {
        Cardfactory::setupCard(card);
        std::cout<<"昆虫类 Card created: %s", card->getName().c_str();
    }
};

class Unclassified:public Cardfactory{
public:
    virtual std::unique_ptr<Card> createCard(std::string name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race) {
        return std::make_unique<Card>(name,HP,ATK,property,cost,race);
    }
protected:
    virtual void setupCard(Card* card) {
        Cardfactory::setupCard(card);
        std::cout<<"无类别 Card created: %s", card->getName().c_str();
    }
};


class squirrel:public Cardfactory{
public:
    virtual std::unique_ptr<Card> createCard(std::string name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race) {
        return std::make_unique<Card>(name,HP,ATK,property,cost,race);
    }
protected:
    virtual void setupCard(Card* card) {
        Cardfactory::setupCard(card);
        std::cout<<"松鼠 Card created: %s", card->getName().c_str();
    }
};

class terrain:public Cardfactory{
public:
    virtual std::unique_ptr<Card> createCard(std::string name,int HP,int ATK,
        std::string property,std::unordered_multimap<std::string,int> cost,std::string race) {
        return std::make_unique<Card>(name,HP,ATK,property,cost,race);
    }
protected:
    virtual void setupCard(Card* card) {
        Cardfactory::setupCard(card);
        std::cout<<"地形 Card created: %s", card->getName().c_str();
    }
};


class CardRandomizer {
private:
    std::vector<std::unique_ptr<Card>> cardCollection;
   
    std::unique_ptr<Card> squirrelCard;
    std::random_device rd;
    std::mt19937 gen;
    int iniflags = 0;
    
public:
    CardRandomizer() : gen(rd()) {
        // 创建所有卡牌并存储
        initializeCardCollection();
        initializesquirrelCard();
    }
    
    void initializesquirrelCard(){
        auto methodsquirrelFactory = std::make_unique<squirrel>();
        squirrelCard=methodsquirrelFactory->createCardwithsetup("松鼠",1,0,"",{}, "松鼠");
    }

    void initializeCardCollection() {
        // 使用工厂创建卡牌并转移到vector中
        auto methodcanoideaFactory = std::make_unique<reptilia>();
        cardCollection.push_back(
            methodcanoideaFactory->createCardwithsetup("牛蛙",2,1,"高跳",{{"血滴",1}}, "爬行类")
        );
        
        auto methodUngulataFactory = std::make_unique<Ungulata>();
        cardCollection.push_back(
            methodUngulataFactory->createCardwithsetup("黑山羊",1,0,"优质祭品",{{"血滴",1}}, "有蹄类")
        );
        
        auto methodbirdsFactory = std::make_unique<birds>();
        cardCollection.push_back(
            methodbirdsFactory->createCardwithsetup("游隼",1,1,"空袭 急袭",{{"血滴",1}}, "鸟类")
        );
        
        // auto methodinsectaFactory = std::make_unique<insecta>();
        // cardCollection.push_back(
        //     methodinsectaFactory->createCardwithsetup("工蚁",1,1,"空袭 急袭",{{"血滴",1}}, "昆虫类")
        // );
        
        // auto methodsquirrelFactory = std::make_unique<squirrel>();
        // cardCollection.push_back(
        //     methodsquirrelFactory->createCardwithsetup("松鼠",1,0,"",{}, "松鼠")
        // );
    }
    
    // 随机获取卡牌（返回指针，不转移所有权）
    Card* getRandomCard() {
        if (cardCollection.empty()) {
            return nullptr;
        }
        
        std::uniform_int_distribution<> dis(0, cardCollection.size() - 1);
        int randomIndex = dis(gen);
        // cardCollection[randomIndex]->set_play_current_card_id(iniflags++);;
        Card* card=new Card(*cardCollection[randomIndex]);
        // if(flag!=-1)
        // {
        //     card->set_play_current_card_id(flag);
        // }else{
            card->set_play_current_card_id(iniflags++);
        // }
        // card->set_play_current_card_id(iniflags++);
        return card;
    }

    // 按名获取卡牌
    Card* getcard(std::string name){
        for(auto &card:cardCollection)
        {
            if(card->getName()==name)
            {
                // card->set_play_current_card_id(iniflags++);
                Card* card1=new Card(*card);
                // if(flag!=-1){
                //     card1->set_play_current_card_id(flag);
                // }else{
                    card1->set_play_current_card_id(iniflags++);
                // }
                
                return card1;
            }
        }
    }

    //获取松鼠牌
    Card* getsquirrel(){
        // squirrel factory;
        // std::unique_ptr<Card> squirrelCard = factory.createCardwithsetup("松鼠",1,0,"",{}, "松鼠");
        // // 获取原始指针（注意：返回后需要调用者管理内存）
        // squirrelCard->set_play_current_card_id(iniflags++);
        Card* card1=new Card(*squirrelCard);
        // if(flag!=-1)
        // {
        //      card1->set_play_current_card_id(flag);
        // }else {
            card1->set_play_current_card_id(iniflags++);
        // }
        return card1;
    }

    //获取鸽子牌
    // Card* getskip(std::string name){
    //     // 创建一个 Unclassified 工厂
    //     Unclassified factory;
    //     // 使用工厂创建 skip 卡牌
    //     std::unique_ptr<Card> skipCard = factory.createCardwithsetup(name,0,0,"",{}, "skip");
        
    //     // 获取原始指针（注意：返回后需要调用者管理内存）
    //     return skipCard.release(); // 转移所有权给调用者
    // }
    
   
    
    // 打印所有卡牌
    void printAllCards() const {
        for (const auto& card : cardCollection) {
            std::cout << "卡牌: " << card->getName() << std::endl;
            std::cout << "属性: " << card->getproperty() << std::endl;
            std::cout << "攻击: " << card->getATK() << std::endl;
            std::cout << "血量: " << card->getHP() << std::endl;
            std::cout << "费用: " << std::endl;
            for(auto i:card->getcost())
            {
                std::cout<<"%s: %d",i.first.c_str(),i.second;
            }
        
            std::cout << "种族: " << card->getrace() << std::endl;
        }
    }
};

#endif