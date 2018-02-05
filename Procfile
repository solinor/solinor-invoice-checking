web: gunicorn -w 3 invoice_checking.wsgi --log-file -
worker: python manage.py process_update_queue

