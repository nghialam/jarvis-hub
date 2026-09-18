"""
api/__init__.py — Blueprint registration for JH3.0

All API routes are organized into blueprints. This module:
1. Imports every blueprint
2. Registers them with the Flask app under /api/v1/* prefixes
3. Registers proxy routes for legacy /api/* paths that map to blueprints

The blueprint layer is the migration target; app.py routes are the
current canonical paths. Over time, frontend code should shift to
/api/v1/* and app.py routes can be pruned.
"""

from flask import jsonify


def register_blueprints(app):
    """Register all API blueprints on the Flask app."""
    from api.main import main_bp
    from api.news import news_bp
    from api.stocks import stocks_bp
    from api.screener import screener_bp
    from api.intelligence import intelligence_bp
    from api.cms import cms_bp
    from api.research import research_bp
    from api.portfolio import portfolio_bp
    from api.llm import llm_bp
    from api.auth import auth_bp
    from api.events import bp as events_bp

    # Register blueprints with correct url_prefixes
    app.register_blueprint(main_bp, url_prefix="/")
    app.register_blueprint(news_bp, url_prefix="/api/v1/news")
    app.register_blueprint(stocks_bp, url_prefix="/api/v1/stocks")
    app.register_blueprint(screener_bp, url_prefix="/api/v1/screener")
    app.register_blueprint(intelligence_bp, url_prefix="/api/v1/intelligence")
    app.register_blueprint(cms_bp, url_prefix="/api/v1/cms")
    app.register_blueprint(research_bp, url_prefix="/api/v1/research")
    app.register_blueprint(portfolio_bp, url_prefix="/api/v1/portfolio")
    app.register_blueprint(llm_bp, url_prefix="/api/v1/llm")
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(events_bp, url_prefix="/api/v1/events")

    # Collect all routes that blueprints already own (to avoid duplicates)
    existing_routes = set()
    for r in app.url_map.iter_rules():
        # blueprint routes have endpoint like "news_bp.get_trending"
        if '.' in r.endpoint and not r.endpoint.startswith('proxy_'):
            existing_routes.add((r.rule, tuple(sorted(r.methods - {'HEAD', 'OPTIONS'}))))

    # Register proxy routes for legacy /api/* paths
    _register_legacy_proxies(app, existing_routes)

    app.logger.info("Registered %d blueprints + proxy routes", 9)


def _register_legacy_proxies(app, skip_existing):
    """
    Register proxy routes that forward legacy /api/* URLs to blueprint
    endpoints. Only registers routes NOT already covered by blueprints.
    """
    # Map: (method, path_template) -> (blueprint_name, endpoint_func)
    PROXY_MAP = [
        # Health & status (already covered by main_bp)
        # ("GET", "/health", ...) — skip, main_bp covers it

        # News: /api/v1/news/* already covered by news_bp url_prefix — skip
        # Proxy only for non-v1 legacy paths (future-proofing)

        # Stocks: /api/v1/stocks/* already covered by stocks_bp url_prefix — skip

        # Screener: /api/v1/screener/* already covered — skip

        # Intelligence: /api/v1/intelligence/* already covered — skip

        # CMS: /api/v1/cms/* already covered — skip

        # Research: /api/v1/research/* already covered — skip

        # Portfolio: /api/v1/portfolio/* already covered — skip

        # LLM Gateway: /api/v1/llm/* already covered — skip

        # Auth: /api/v1/auth/* already covered — skip

        # Legacy /api/ paths NOT in blueprints (for when blueprints get these)
        # Currently empty — all /api/v1/* are already in blueprints
        # Legacy /api/ paths are still served by app.py routes

        # Add any legacy proxy routes here as they're migrated:
        # ("GET", "/api/somelegacy", "news_bp", "get_trending"),
    ]

    for method, path, blueprint_name, endpoint_name in PROXY_MAP:
        route_key = (path, (method,))
        if route_key in skip_existing:
            app.logger.debug("Skipping proxy for %s %s (already in blueprint)", method, path)
            continue

        # Generate unique endpoint name
        ep_name = f"proxy_{blueprint_name}_{endpoint_name}"
        app.add_url_rule(
            path,
            endpoint=ep_name,
            view_func=_make_proxy(app, blueprint_name, endpoint_name),
        )
        app.logger.info("Registered proxy %s %s -> %s.%s", method, path, blueprint_name, endpoint_name)


def _make_proxy(app, bname, ename):
    """Factory to create a proxy endpoint function with proper closure."""
    def proxy_endpoint(**kwargs):
        """Proxy a route to the blueprint endpoint."""
        bp = app.blueprints.get(bname)
        if bp is None:
            return jsonify({"error": f"Blueprint {bname} not found"}), 500
        endpoint_fn = bp.view_functions.get(ename)
        if endpoint_fn is None:
            return jsonify({"error": f"Endpoint {ename} not found in {bname}"}), 500
        try:
            return endpoint_fn(**kwargs)
        except Exception as e:
            app.logger.error("Proxy error %s %s -> %s.%s: %s",
                           proxy_endpoint.__name__, bname, ename, e)
            return jsonify({"error": str(e)}), 500
    return proxy_endpoint
