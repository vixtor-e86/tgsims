from urllib.parse import parse_qs
from app import create_app

app = create_app()


class VercelPathMiddleware:
    """
    Middleware to normalize PATH_INFO for Vercel serverless function invocations.
    When Vercel rewrites incoming traffic to /api/index?__path=/$1, this middleware
    extracts the intended path and restores it in WSGI environ['PATH_INFO'].
    """

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        query_string = environ.get('QUERY_STRING', '')
        params = parse_qs(query_string)
        if '__path' in params and params['__path']:
            target_path = params['__path'][0]
            if not target_path.startswith('/'):
                target_path = '/' + target_path
            environ['PATH_INFO'] = target_path
        elif environ.get('PATH_INFO') in ('/api/index', '/api/index.py', '/api', '/api/'):
            environ['PATH_INFO'] = '/'

        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
handler = app
