# MSG HRIT — Documentation PDFs

Generated from the in-app product reference glossary and local sample imagery.

| File | Description |
|------|-------------|
| `MSG_HRIT_Product_Interpretation_Applications_Report.pdf` | Full interpretation report for every SEVIRI channel and composite, with sector applications (Agriculture, Aviation, Natural Resource Monitoring, Natural Disaster Monitoring) and example images. |
| `MSG_HRIT_Product_User_Guide_Two_Pager.pdf` | Printable **two-page sheet per product** (identity + image on page 1; four sector applications + tips on page 2). |

## Regenerate

```bash
backend\.venv\Scripts\python docs\generate_product_pdfs.py
```

Requires `reportlab` and `pillow` in the backend virtualenv. Sample images are read from `data/processed/` (daytime `2026-06-22/09-00`, night fallback `20-00`).
