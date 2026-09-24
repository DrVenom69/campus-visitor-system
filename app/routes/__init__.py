"""Every blueprint lives in its own module so teammates can work without merge conflicts."""


def register_blueprints(app):
    from app.routes import auth, dashboard, gate, history, public, requests, users

    for module in (public, auth, dashboard, requests, users, gate, history):
        app.register_blueprint(module.bp)
