# Catalog matcher on 295 labelled listings

## brand site (bar today 0.85)

148 listings, 129 whose product the catalog has; exact names 32 (1 wrong).

| bar | trusted | right product | wrong | precision | recall | right entry |
|---|---|---|---|---|---|---|
| 0.5 | 112 | 103 | 9 | 0.92 | 0.798 | 99/99 |
| 0.6 | 106 | 99 | 7 | 0.934 | 0.767 | 95/95 |
| 0.7 | 99 | 93 | 6 | 0.939 | 0.721 | 90/90 |
| 0.8 | 87 | 82 | 5 | 0.943 | 0.636 | 79/79 |
| 0.85 | 84 | 80 | 4 | 0.952 | 0.62 | 78/78 |
| 0.9 | 82 | 79 | 3 | 0.963 | 0.612 | 78/78 |
| 0.95 | 72 | 69 | 3 | 0.958 | 0.535 | 68/68 |

## store-built (bar today 0.9)

147 listings, 107 whose product the catalog has; exact names 33 (0 wrong).

| bar | trusted | right product | wrong | precision | recall | right entry |
|---|---|---|---|---|---|---|
| 0.5 | 104 | 99 | 5 | 0.952 | 0.925 | 85/86 |
| 0.6 | 99 | 97 | 2 | 0.98 | 0.907 | 85/86 |
| 0.7 | 94 | 93 | 1 | 0.989 | 0.869 | 83/84 |
| 0.8 | 89 | 88 | 1 | 0.989 | 0.822 | 81/82 |
| 0.85 | 85 | 84 | 1 | 0.988 | 0.785 | 79/80 |
| 0.9 | 79 | 78 | 1 | 0.987 | 0.729 | 76/77 |
| 0.95 | 73 | 72 | 1 | 0.986 | 0.673 | 71/71 |

## all

295 listings, 236 whose product the catalog has; exact names 65 (1 wrong).

| bar | trusted | right product | wrong | precision | recall | right entry |
|---|---|---|---|---|---|---|
| 0.5 | 216 | 202 | 14 | 0.935 | 0.856 | 184/185 |
| 0.6 | 205 | 196 | 9 | 0.956 | 0.831 | 180/181 |
| 0.7 | 193 | 186 | 7 | 0.964 | 0.788 | 173/174 |
| 0.8 | 176 | 170 | 6 | 0.966 | 0.72 | 160/161 |
| 0.85 | 169 | 164 | 5 | 0.97 | 0.695 | 157/158 |
| 0.9 | 161 | 157 | 4 | 0.975 | 0.665 | 154/155 |
| 0.95 | 145 | 141 | 4 | 0.972 | 0.597 | 139/139 |

## Trusted today and wrong

- Grön: 'Milk Chocolate Sea Salt -Sativa- 1:1 THC:CBG 100mg Chocolate Mini Bar (Edibles) | Grön    -RR2 BACK' -> 'Milk Chocolate Sea Salt' (exact 1.0); label 'Mini Bar 1:1 Milk Chocolate'
- Off Hours: 'Off hours | Effect Based Rope 100mg | Melt (calm)' -> 'Melt' (jev 0.97); label 'Melt Blueberry Pie'
- Off Hours: 'Off Hours - Rope Party Animal (Party)' -> 'Party Party Animal' (jev 0.89); label 'Party Animal Passion Pop'
- Layup: 'Lemonade Variety Pack - 8 x 10MG Beverages' -> 'Lemonade' (jev 0.97); label None
- Grassroots: 'Foreign Kush Mints -Indica- 34.72% THC | 14g (Flower) (Dark Heart Collection) | Grassroots  - AA8 FRONT' -> 'Dark Heart Collection Foreign Kush Mints' (jev 0.99); label None
