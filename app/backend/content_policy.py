"""Discovery category is a platform source selection, not a project rewrite."""
def content_policy(rules):
    result = dict(rules)
    if result.get("contentFitCategory"):
        result["category"] = result["contentFitCategory"]
    # Platform sale-type labels are aliases of the existing content requirement.
    # Do not invalidate an unchanged work judgment after the new selector label.
    result["contentType"] = {"视频达人": "短视频", "直播达人": "直播",
                             "图文达人": "图文", "橱窗达人": "橱窗"}.get(
        result.get("contentType"), result.get("contentType"))
    return result
