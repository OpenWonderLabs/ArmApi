#include "onero_gripper.h"
#include <filesystem>
#include <iostream>
int main(int argc, char** argv) {
    if (argc != 2 || std::filesystem::exists(argv[1])) return 2;
    onero_gripper_api::OneroGripper gripper(argv[1]);
    if (gripper.valid() || gripper.status().valid || gripper.get_tactile().valid) return 1;
    std::cout << "gripper C++ invalid-device status/tactile: OK\n";
    return 0;
}
