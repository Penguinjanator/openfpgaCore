/* Host boundary for the real mixer HAL. No audio or allocation logic lives here. */
#ifndef TEST_MIXER_MOCK_H
#define TEST_MIXER_MOCK_H
#include <stdint.h>
#include "target_platform.h"

static uint32_t test_irq_save(void);
static void test_irq_restore(uint32_t prev);
static volatile uint32_t *test_reg(unsigned offset);
static volatile uint32_t *test_pending(void);
static volatile uint32_t *test_clear(void);

#define MIX_VOICE_FIELD(v, f) (*test_reg(((v) << 6) + ((f) << 2)))
#define MIX_VOICE_ADDR(v) MIX_VOICE_FIELD(v, 0)
#define MIX_VOICE_LEN(v) MIX_VOICE_FIELD(v, 1)
#define MIX_VOICE_RATE(v) MIX_VOICE_FIELD(v, 2)
#define MIX_VOICE_CTRL(v) MIX_VOICE_FIELD(v, 3)
#define MIX_VOICE_POS_WR(v) MIX_VOICE_FIELD(v, 4)
#define MIX_VOICE_VOL_LR(v) MIX_VOICE_FIELD(v, 6)
#define MIX_VOICE_LOOP_END(v) MIX_VOICE_FIELD(v, 7)
#define MIX_VOICE_LOOP_START(v) MIX_VOICE_FIELD(v, 8)
#define MIX_VOICE_VOL_TARGET(v) MIX_VOICE_FIELD(v, 9)
#define MIX_VOICE_VOL_RATE(v) MIX_VOICE_FIELD(v, 10)
#define MIX_MASTER_VOL (*test_reg(0x800))
#define MIX_GROUP_VOL(g) (*test_reg(0x804 + ((g) << 2)))
#define MIX_VOICE_GROUP_LO (*test_reg(0x814))
#define MIX_VOICE_GROUP_HI (*test_reg(0x818))
#define MIX_CTRL (*test_reg(0x820))
#define MIX_CTRL_ENABLE 1
#define MIX_IRQ_PENDING (*test_pending())
#define MIX_IRQ_CLEAR (*test_clear())
#define MIX_ACTIVE_MASK (*test_reg(0x830))
#define MIX_VOICE_POS(v) (*test_reg(0x880 + ((v) << 2)))
#endif
