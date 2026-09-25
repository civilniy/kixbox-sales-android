from sections import (ads, competitors, crm, customers, logistics, overview, products, sales, stock, stores,
                      traffic)

SECTIONS = [overview, sales, products, stores, customers, traffic, ads, crm, logistics, stock, competitors]
BY_ID = {s.ID: s for s in SECTIONS}
