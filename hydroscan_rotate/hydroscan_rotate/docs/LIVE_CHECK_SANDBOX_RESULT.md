> **Run inside the build sandbox, which blocks NASA, ISRIC and Google hosts. This is NOT evidence of the services' real behaviour; it only shows the tool reports failures honestly.**

# Live data check
Run at 2026-11-14T18:42:58. GEE project configured: False.

## Sakha (31.117, 30.95)

| Source | Result | Retrieved | Period | Resolution | Evidence / reason |
|---|---|---|---|---|---|
| NASA POWER daily | **FAIL** | - | - | - | ConnectionError: HTTPSConnectionPool(host='power.larc.nasa.gov', port=443): Max retries exceeded with url: /api/temporal/daily/point?parameters=T2M%2CT2M_MAX%2CT2M_MIN%2CPRECTOT |
| ISRIC SoilGrids (WCS -> GEE -> REST) | **FAIL** | - | - | - | WCS failed: WCS sand 0-5cm: ConnectionError: HTTPSConnectionPool(host='maps.isric.org', port=443): Max retries exceeded with url: /mapserv?map=%2Fmap%2Fsand.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverag | REST failed: REST: ConnectionError: HTTPSConnectionPool(host='rest.isric.org', port=443): Max retries exceeded with url: /soilgrids/v2.0/properties/query?lon=30.95&lat=31.117&value=mean&property=s |
| Sentinel-2 NDVI via GEE | **SKIPPED** | - | - | - | HYDROSCAN_GEE_PROJECT is not set (see SETUP_GUIDE.md) |
| GPM IMERG via GEE | **SKIPPED** | - | - | - | HYDROSCAN_GEE_PROJECT is not set (see SETUP_GUIDE.md) |
| SMAP via GEE | **SKIPPED** | - | - | - | HYDROSCAN_GEE_PROJECT is not set (see SETUP_GUIDE.md) |
