from aiogram.fsm.state import State, StatesGroup


class AddChannelState(StatesGroup):
    waiting_for_url = State()
    running = State()
    waiting_for_initial_scan_choice = State()


class CustomDateRangeState(StatesGroup):
    waiting_for_start_date = State()
    waiting_for_end_date = State()


class SettingsState(StatesGroup):
    waiting_for_keyword = State()
    waiting_for_new_admin_id = State()


class ChannelPriceState(StatesGroup):
    waiting_for_cpm = State()
