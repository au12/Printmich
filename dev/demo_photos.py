"""Demo library used for development and README screenshots.

Photos come from Unsplash (https://unsplash.com/license — free to use). Run
`python dev/demo_photos.py /tmp/demo/lib` to download them; dev/mock_immich.py
serves them through an Immich-compatible API.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

#  unsplash id,                    file name,      city, state, country,           taken,                fav, ★, albums, people, description
PHOTOS = [
    ("1418065460487-3e41a6c84dc5", "DSC04411.jpg", "Forks", "Washington", "United States", "2021-10-03T08:14:00", 1, 5, ["National Parks"], [], "Morning fog over the Hoh"),
    ("1418489098061-ce87b5dc3aee", "IMG_2210.jpg", "Portland", "Oregon", "United States", "2024-04-12T17:42:00", 0, 4, [], [], ""),
    ("1426604966848-d7adac402bff", "DSC09122.jpg", "Yosemite Valley", "California", "United States", "2019-11-16T16:58:00", 1, 5, ["Yosemite & the Sierra", "National Parks"], [], "El Capitan, late light"),
    ("1431794062232-2a99a5431c6c", "DSC07730.jpg", "Springdale", "Utah", "United States", "2022-05-21T11:05:00", 0, 4, ["National Parks"], [], ""),
    ("1433086966358-54859d0ed716", "IMG_0412.jpg", "Bridal Veil", "Oregon", "United States", "2018-11-15T10:20:00", 1, 5, ["National Parks"], [], "Multnomah Falls"),
    ("1441974231531-c6227db76b6e", "IMG_8841.jpg", "Orick", "California", "United States", "2020-06-30T09:31:00", 0, 3, ["National Parks"], [], ""),
    ("1446776811953-b23d57bd21aa", "iss064e025014.jpg", None, None, None, "2017-03-02T14:00:00", 0, 4, [], [], "Earth from the ISS (NASA)"),
    ("1447752875215-b2761acb3c5d", "IMG_6620.jpg", "North Vancouver", "British Columbia", "Canada", "2023-08-19T13:12:00", 0, 3, [], [], ""),
    ("1449824913935-59a10b8d2000", "IMG_1188.jpg", "New York", "New York", "United States", "2022-11-17T12:40:00", 0, 0, ["City Breaks"], [], ""),
    ("1454496522488-7a8e488e8606", "DSC02210.jpg", "Khumjung", "Koshi", "Nepal", "2016-04-28T06:12:00", 1, 5, ["Best of the Archive"], [], "Ama Dablam at dawn"),
    ("1462331940025-496dfbfc7564", "bubble-nebula.jpg", None, None, None, "2016-04-21T21:00:00", 0, 4, [], [], "The Bubble Nebula (NASA/ESA)"),
    ("1464822759023-fed622ff2c3b", "DSC05011.jpg", "Twizel", "Canterbury", "New Zealand", "2019-02-09T15:22:00", 1, 4, ["Best of the Archive"], [], ""),
    ("1465146344425-f00d5f5c8f07", "IMG_3304.jpg", "Valensole", "Provence", "France", "2023-06-04T19:01:00", 0, 4, [], [], "Poppies"),
    ("1470071459604-3b5ec3a7fe05", "DSC03301.jpg", "Funchal", "Madeira", "Portugal", "2024-02-11T08:50:00", 1, 5, ["Best of the Archive"], [], "Above the clouds"),
    ("1470770841072-f978cf4d019e", "DSC00187.jpg", "Braies", "South Tyrol", "Italy", "2021-11-14T09:15:00", 1, 5, ["Dolomites 2021"], [], "The boathouse at Braies"),
    ("1472214103451-9374bd1c798e", "DSC04478.jpg", "Uig", "Isle of Skye", "United Kingdom", "2017-09-12T19:30:00", 0, 5, ["Best of the Archive"], [], "Fairy Glen sunset"),
    ("1475924156734-496f6cac6ec1", "DSC08821.jpg", "Big Sur", "California", "United States", "2020-01-25T17:20:00", 0, 4, [], [], ""),
    ("1477959858617-67f85cf4f1df", "IMG_5512.jpg", "Chicago", "Illinois", "United States", "2025-07-04T18:10:00", 0, 3, ["City Breaks"], [], ""),
    ("1480714378408-67cf0d13bc1b", "IMG_7730.jpg", "New York", "New York", "United States", "2022-11-18T16:22:00", 1, 4, ["City Breaks"], [], "Golden hour, Midtown"),
    ("1482192596544-9eb780fc7f66", "DJI_0042.jpg", "Feldberg", "Baden-Württemberg", "Germany", "2018-10-07T07:44:00", 0, 3, [], [], ""),
    ("1490645935967-10de6ba17061", "IMG_9101.jpg", "Portland", "Oregon", "United States", "2025-03-09T11:02:00", 0, 3, ["Food & Coffee"], [], "Sunday brunch"),
    ("1490750967868-88aa4486c946", "IMG_2271.jpg", "Lancaster", "California", "United States", "2019-03-30T10:12:00", 0, 4, [], [], "Superbloom"),
    ("1494500764479-0c8f2919a3d8", "DSC01180.jpg", "Wanaka", "Otago", "New Zealand", "2019-02-14T20:51:00", 1, 5, ["Best of the Archive"], [], "That Wanaka Tree"),
    ("1497436072909-60f360e1d4b1", "DJI_0310.jpg", "Lake Louise", "Alberta", "Canada", "2023-07-22T12:33:00", 0, 4, ["National Parks"], [], ""),
    ("1500530855697-b586d89ba3ee", "DSC06612.jpg", "Overton", "Nevada", "United States", "2020-11-16T15:48:00", 0, 4, [], [], "Valley of Fire road"),
    ("1500534314209-a25ddb2bd429", "IMG_4402.jpg", "Gatlinburg", "Tennessee", "United States", "2024-10-26T18:05:00", 1, 4, ["National Parks"], [], "Smoky Mountain layers"),
    ("1500622944204-b135684e99fd", "DSC00921.jpg", "Ninh Bình", None, "Vietnam", "2018-08-03T06:58:00", 0, 4, [], [], ""),
    ("1501594907352-04cda38ebc29", "IMG_3550.jpg", "San Francisco", "California", "United States", "2021-05-15T14:30:00", 1, 4, ["City Breaks"], [], "Golden Gate"),
    ("1501785888041-af3ef285b470", "DSC00266.jpg", "Braies", "South Tyrol", "Italy", "2021-11-15T11:41:00", 0, 4, ["Dolomites 2021"], [], ""),
    ("1502082553048-f009c37129b9", "DSC02991.jpg", "Serengeti", "Mara", "Tanzania", "2017-07-19T16:16:00", 0, 4, [], [], ""),
    ("1504674900247-0877df9cc836", "IMG_8012.jpg", "Portland", "Oregon", "United States", "2025-09-20T19:47:00", 0, 3, ["Food & Coffee"], [], "Date night"),
    ("1505228395891-9a51e7e86bf6", "DJI_0518.jpg", "Kīhei", "Hawaii", "United States", "2022-03-01T10:25:00", 0, 4, [], [], ""),
    ("1506744038136-46273834b3fb", "DSC09160.jpg", "Yosemite Valley", "California", "United States", "2019-11-17T07:21:00", 1, 5, ["Yosemite & the Sierra", "National Parks"], [], "Merced River morning"),
    ("1507525428034-b723cf961d3e", "IMG_6001.jpg", "Tulum", "Quintana Roo", "Mexico", "2024-06-23T20:14:00", 0, 4, [], [], ""),
    ("1509042239860-f550ce710b93", "IMG_4101.jpg", "Madison", "Wisconsin", "United States", "2025-11-16T09:12:00", 0, 3, ["Food & Coffee"], [], "Third round"),
    ("1511497584788-876760111969", "DSC07102.jpg", "Banff", "Alberta", "Canada", "2023-07-24T20:59:00", 0, 4, ["National Parks"], [], ""),
    ("1514565131-fce0801e5785", "IMG_0911.jpg", "Jersey City", "New Jersey", "United States", "2022-11-16T17:03:00", 0, 3, ["City Breaks"], [], ""),
    ("1514888286974-6c03e2ca1dba", "IMG_7442.jpg", "Madison", "Wisconsin", "United States", "2024-01-05T12:44:00", 1, 5, ["The Pets"], ["Pepper"], "Pepper"),
    ("1517849845537-4d257902454a", "IMG_7801.jpg", "Madison", "Wisconsin", "United States", "2025-05-30T16:20:00", 1, 4, ["The Pets"], ["Waffles"], ""),
    ("1519681393784-d120267933ba", "DSC03344.jpg", "Ashford", "Washington", "United States", "2021-08-12T23:14:00", 1, 5, ["Best of the Archive"], [], "Milky Way over Rainier"),
    ("1523712999610-f77fbcfc3843", "DSC05512.jpg", "Luray", "Virginia", "United States", "2020-10-24T07:38:00", 0, 4, [], [], ""),
    ("1543466835-00a7907e9de1", "IMG_9930.jpg", "Madison", "Wisconsin", "United States", "2026-11-14T15:05:00", 1, 5, ["The Pets"], ["Biscuit"], "Biscuit"),
]

CAMERAS = [
    ("SONY", "ILCE-7RM5", "FE 24-70mm F2.8 GM II"),
    ("Apple", "iPhone 16 Pro", "iPhone 16 Pro back triple camera 6.765mm f/1.78"),
    ("FUJIFILM", "X-T5", "XF16-55mmF2.8 R LM WR"),
    ("Canon", "Canon EOS R6m2", "RF24-105mm F4 L IS USM"),
    ("DJI", "FC8482", "24.0 mm f/1.7"),
]


def download(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for uid, *_ in PHOTOS:
        out = dest / f"{uid}.jpg"
        if out.exists():
            continue
        url = f"https://images.unsplash.com/photo-{uid}?w=2400&q=88&fm=jpg"
        print("downloading", url)
        urllib.request.urlretrieve(url, out)


if __name__ == "__main__":
    download(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/demo/lib"))
