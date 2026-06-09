from aiogram.fsm.state import State, StatesGroup


class LotteryAdminStates(StatesGroup):
    waiting_title = State()
    waiting_auto_draw = State()
