import os


ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "prokop_jan@gymbn.cz").strip().casefold()
SHADOW_ACCOUNT_EMAIL = "prokop_jan@gbn.cz"
ADMIN_EMAILS = frozenset({ADMIN_EMAIL, SHADOW_ACCOUNT_EMAIL})