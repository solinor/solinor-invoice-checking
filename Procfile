# There is a reason not to increase -w -- this project uses persistent database connections (as every page requires database operations), and you'll hit database connection limit.
web: gunicorn -w 3 invoice_checking.wsgi --log-file -
worker: python manage.py process_update_queue
