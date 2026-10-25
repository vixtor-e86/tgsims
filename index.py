from app import create_app

app = create_app()


class VercelPathMiddleware:
    """
    Middleware to normalize PATH_INFO for Vercel serverless function invocations.
    When Vercel rewrites incoming traffic to /api/index, WSGI can receive /api/index
    instead of the user's actual URL. This middleware restores the intended path.
    """

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path in ('/api/index', '/api/index.py', '/api', '/api/'):
            matched = environ.get('HTTP_X_MATCHED_PATH')
            if matched and not matched.startswith('/api/index'):
                environ['PATH_INFO'] = matched
            else:
                environ['PATH_INFO'] = '/'
        elif path.startswith('/api/index/'):
            environ['PATH_INFO'] = path[len('/api/index'):]
        elif path.startswith('/api/index.py/'):
            environ['PATH_INFO'] = path[len('/api/index.py'):]

        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
handler = app
