"""Versioned brand exports; admission evidence remains in the source pool."""
BODY_FIELDS = ("身高(cm)", "体重(斤)", "内衣单品", "内衣单品近30天短视频销售额", "关联短视频数", "关联直播场次")

def apply_template(delivery, strategy):
    category = str(strategy.get("category") or "")
    apparel = "内衣" in category or any(strategy.get(key) for key in ("requireBodyMeasurements", "requireShapewearContent", "minimumUnderwearProductSales"))
    excluded = [] if apparel else list(BODY_FIELDS)
    delivery["rows"] = [{key: value for key, value in row.items() if key not in excluded} for row in delivery.get("rows", [])]
    delivery["export_template"] = {"name":"服饰内衣" if apparel else "品牌通用", "version":3, "excluded_fields":excluded}
    return delivery
