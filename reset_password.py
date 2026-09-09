import getpass
import sys

from werkzeug.security import generate_password_hash

import main


if len(sys.argv) != 2:
    raise SystemExit("Usage: python reset_password.py account-email")

email = sys.argv[1].strip().lower()
new_password = getpass.getpass("New password: ")
if len(new_password) < 8:
    raise SystemExit("Password must be at least 8 characters.")

with main.app.app_context():
    user = main.db.session.scalar(main.db.select(main.User).where(main.User.email == email))
    if user is None:
        raise SystemExit("No account found for that email.")
    user.password = generate_password_hash(new_password)
    main.db.session.commit()
    print(f"Password updated for {user.email}.")
