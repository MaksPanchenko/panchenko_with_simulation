#include "multiwii/status.hpp"
#include <msp/msp_msg.hpp>
#include <gtest/gtest.h>

TEST(Status, ReorderedSparseBoxes) {
    const std::vector<std::string> names{"HORIZON", "ARM", "FAILSAFE", "ANGLE", "BEEPER"};
    EXPECT_EQ(multiwii::arm_index(names), 1u);
    EXPECT_EQ(multiwii::flight_mode(names, {}), "ACRO");
    EXPECT_EQ(multiwii::flight_mode(names, {1, 3, 4}), "ANGLE");
    EXPECT_EQ(multiwii::flight_mode(names, {0, 1, 3}), "HORIZON");
    EXPECT_EQ(multiwii::flight_mode(names, {0, 1, 2, 3}), "FAILSAFE");
    EXPECT_THROW(multiwii::arm_index({"ANGLE"}), std::runtime_error);
    EXPECT_THROW(multiwii::arm_index({"ARM", "ARM"}), std::runtime_error);
    auto too_many = std::vector<std::string>(32, "OTHER");
    too_many.push_back("ARM");
    EXPECT_THROW(multiwii::arm_index(too_many), std::runtime_error);
}

TEST(Status, LegacyAndExtendedWireLayouts) {
    for(const auto variant : {msp::FirmwareVariant::MWII, msp::FirmwareVariant::CLFL,
                             msp::FirmwareVariant::BTFL}) {
        msp::msg::Status status(variant);
        const msp::ByteVector legacy(std::vector<uint8_t>{0xe8, 3, 0, 0, 7, 0, 2, 0, 0, 128, 0});
        EXPECT_TRUE(status.decode(legacy));
        EXPECT_EQ(status.box_mode_flags, (std::set<std::size_t>{1, 31}));
        const msp::ByteVector extended(std::vector<uint8_t>{0xe8, 3, 0, 0, 7, 0, 8, 0, 0, 0, 0, 10, 0, 0xe8, 3});
        EXPECT_TRUE(status.decode(extended));
        EXPECT_EQ(status.box_mode_flags, (std::set<std::size_t>{3}));
        EXPECT_FALSE(status.decode(msp::ByteVector(std::vector<uint8_t>{0, 0, 0})));
    }
}
