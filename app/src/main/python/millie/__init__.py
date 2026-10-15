__version__ = "3.0.0"

def start_server(port=8770, host="127.0.0.1"):
    from .web.server import serve
    serve(host=host, port=port, autostart=True)
