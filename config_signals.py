# config_signals.py

CONFIRM_MIN_AGE_MIN = 20        # минимум минут после листинга
CONFIRM_MAX_AGE_MIN = 180       # максимум (пока первая волна жива)

CONFIRM_VOLUME_MULTIPLIER = 1.7 # объём вырос минимум в 1.7 раза
CONFIRM_PRICE_DROP_MAX = -0.05  # цена не падала больше чем на -5%

CONFIRM_MIN_VOLUME_USD = 300_000
# CONFIRM-LIGHT (ранний вход)
CONFIRM_LIGHT_ENABLED = True

# Минимальный рост объёма между проверками
CONFIRM_LIGHT_VOL_MULT = 1.25   # +25%

# Минимальное время после первого обнаружения (в минутах)
CONFIRM_LIGHT_MIN_MINUTES = 20

# Максимальный возраст монеты для CONFIRM-LIGHT
CONFIRM_LIGHT_MAX_AGE_DAYS = 2
