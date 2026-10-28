# Проверка архива «Attachments-Fw_ 27.10 avito.zip» (восьмой исходный ZIP)

**Источник:** [`usaforyou/MANUS1/Attachments-Fw_ 27.10 avito.zip`](https://github.com/usaforyou/MANUS1/blob/main/Attachments-Fw_%2027.10%20avito.zip), добавлен коммитом `68d7c1f7cb99d3f47a4159bf3ff93d80b194e8fe` 28.10.2026 13:03:40 UTC. SHA-256 архива: `216adc3cb760c13c5ea85da0a8cf0a5baf9ecb51748ec4619ad4c456bcbc349c`, размер 669 505 байт, 10 записей. Сам ZIP в репозиторий не копировался; HTML/JS в архиве отсутствуют и не исполнялись.

## Состав и безопасность

- **7 текстовых записей** `text*.txt` — не текст, а Apple-бинарные плist’ы (`bplist00`, `NSKeyedArchiver`): содержимое буфера обмена/iOS-шаринга. Разобраны стандартной библиотекой `plistlib`, ничего не исполнялось. Расшифровки сохранены как [`message_01.txt` … `message_07.txt`](attachments_fw_2026_10_28/).
- **3 фото** `image.`, `image-1.`, `image-2.` (без расширений) — JPEG 960×1280, скопированы побайтово как [`seller_photo_01.jpg` … `seller_photo_03.jpg`](attachments_fw_2026_10_28/).
- Вложенных архивов, PDF, HTML и JS нет. Машинный манифест — [`attachments_fw_2026_10_28/manifest.json`](attachments_fw_2026_10_28/manifest.json); воспроизведение проверки:

```bash
python avito_audit/check_fw_zip.py /path/to/Attachments-Fw_27.10_avito.zip
```

## Что содержат сообщения (продавец «Алина Зуева»)

Сообщение от **25.10.2026 17:18** — ссылка на профиль `https://www.avito.ru/user/b2165ff5492372c90fab55f7223f9d3b/…`, т. е. **тот же профиль, что и в архивном снимке каталога**.

Сообщения от **28.10.2026 13:51** — свежие цены продавца по пяти средствам IMAGE Skincare и описания линеек:

| Средство (по сообщению и OCR фото) | Цена продавца | Статус в каталоге |
| --- | --- | --- |
| The MAX Crème, крем для лица, 48 г («Max face cream») | 11 500 ₽ | нового архивного объявления нет |
| The MAX Eye Crème, 15 мл («Max eye cream») | 6 800 ₽ | нового архивного объявления нет |
| DAILY PREVENTION SPF 30, увлажняющий крем с тинтом и без («SPF 30 мойсчерайзер») | 4 900 ₽ | соответствует объявлению [8166255881](../catalog.json) (архив 5 900 ₽) |
| IMAGE MD Biotech Longevity Crème, 50 г («Biotech MD cream») | 10 400 ₽ | соответствует объявлению 8230842563 (архив 12 999 ₽) |
| IMAGE MD Restoring Power-C Serum, 30 мл («Biotech MD serum») | 11 500 ₽ | **не объединяется** с архивной сывороткой 8165960870 «Restoring Youth Serum» — другой официальный продукт |

## Идентификация фотографий

Подписи на трёх фото прочитаны **машинным OCR** (RapidOCR, локально) и согласованы с текстами сообщений:

- `seller_photo_01.jpg` — IMAGE **the MAX eye creme** «crème contour des yeux», 0.5 fl oz/15 мл, и **the MAX creme**, Net wt. 1.7 oz/48 г;
- `seller_photo_02.jpg` — IMAGE **DAILY PREVENTION** «pure mineral tinted moisturizer» и «pure mineral hydrating moisturizer», Broad Spectrum SPF 30, Net wt. 2.6 oz/73 г (видны оба варианта — с тинтом и без);
- `seller_photo_03.jpg` — IMAGE MD **restoring power-c serum**, 1 fl oz/30 мл, и **biotech longevity creme**, Net wt. 1.7 oz/50 г (XOSM™).

OCR согласован с текстом сообщений, но **не подтверждает подлинность, состояние или комплектацию** экземпляров.

## Границы данных

- Это **заявления продавца в переписке**, а не проверенные данные объявлений: на действующем Avito цены и наличие не проверялись (в песочнице недоступны).
- Сопоставление «сообщение ↔ объявление» выполнено по названию линии и тексту описания для 8166255881 и 8230842563; для остальных трёх средств архивных карточек нет, для сыворотки Power-C сознательно **не объединено** с похожей архивной позицией.
- Побайтовых дубликатов с фотографиями семи предыдущих ZIP нет (сверка SHA-256 по манифестам).
