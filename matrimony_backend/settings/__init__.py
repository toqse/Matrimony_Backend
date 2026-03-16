import os
d = os.environ.get('DJANGO_ENV', 'development')
if d == 'production':
    from .production import *
else:
    from .development import *
