
#include "server1_4_1.hpp"

// 主函数
int main() {
    try {
        std::cout << "Starting Game Server..." << std::endl;
        
        // 创建游戏服务器实例
        auto game_server = std::make_shared<GameServer>();
        
        std::cout << "Game server is running on port 8002. Press Enter to exit..." << std::endl;
        
        // 等待用户输入以保持服务器运行
        std::cin.get();
        
        std::cout << "Shutting down game server..." << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}