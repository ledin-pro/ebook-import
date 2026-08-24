from __future__ import annotations

import base64
import zipfile
from pathlib import Path


def make_epub(path: Path, title: str = "Тестовая книга", *, image: bool = True) -> None:
    container = """<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    image_manifest = '<item id="image" href="images/picture.png" media-type="image/png"/>' if image else ""
    image_html = '<p><img src="images/picture.png" alt="Иллюстрация"/></p>' if image else ""
    opf = f"""<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title><dc:creator>Автор</dc:creator><dc:language>ru</dc:language><dc:date>2024</dc:date><dc:identifier>isbn:9780000000000</dc:identifier></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>{image_manifest}<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest><spine toc="ncx"><itemref idref="chapter"/></spine></package>"""
    ncx = """<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint id="n1"><navLabel><text>Глава 1</text></navLabel><content src="chapter.xhtml#start"/></navPoint></navMap></ncx>"""
    xhtml = f"""<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>ignored</title></head><body><div class="title2">Глава 1</div><p class="p1">Привет, <strong>мир</strong>.</p><div class="cite">Цитата.</div>{image_html}</body></html>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OPS/content.opf", opf)
        archive.writestr("OPS/toc.ncx", ncx)
        archive.writestr("OPS/chapter.xhtml", xhtml)
        if image:
            archive.writestr("OPS/images/picture.png", b"png-fixture")


def fb2_xml(*, encoding: str = "utf-8", binary: str | None = None) -> bytes:
    image_data = base64.b64encode(b"png-fixture").decode("ascii") if binary is None else binary
    text = f'''<?xml version="1.0" encoding="{encoding}"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:xlink="http://www.w3.org/1999/xlink">
  <description>
    <title-info>
      <genre>science</genre>
      <author><first-name>Иван</first-name><middle-name>Иванович</middle-name><last-name>Авторов</last-name></author>
      <book-title>Тестовая FB2 книга</book-title>
      <annotation><p>Описание книги.</p></annotation>
      <date>2025</date><lang>ru</lang>
      <sequence name="Серия" number="2"/>
      <coverpage><image xlink:href="#cover.png"/></coverpage>
    </title-info>
    <document-info><id>doc-123</id></document-info>
    <publish-info><publisher>Издатель</publisher><isbn>978-1-2345-6789-0</isbn></publish-info>
  </description>
  <body>
    <section id="ch1">
      <title><p>Глава первая</p></title>
      <epigraph><p>Эпиграф.</p><text-author>Автор цитаты</text-author></epigraph>
      <p>Обычный <strong>жирный</strong> и <emphasis>курсив</emphasis>. <a type="note" xlink:href="#n1">1</a></p>
      <poem><title><p>Стих</p></title><stanza><v>Строка один</v><v>Строка два</v></stanza></poem>
      <image xlink:href="#cover.png"/>
      <section id="nested"><title><p>Подраздел</p></title><p>Вложенный текст.</p></section>
      <table><tr><th>А</th><th>Б</th></tr><tr><td>1</td><td>2</td></tr></table>
    </section>
    <section id="ch2"><title><p>Глава вторая</p></title><p>Финал.</p></section>
  </body>
  <body name="примечания"><section id="n1"><title><p>Примечание</p></title><p>Текст примечания.</p></section></body>
  <binary id="cover.png" content-type="image/png">{image_data}</binary>
  <binary id="unused.jpg" content-type="image/jpeg">dW51c2Vk</binary>
</FictionBook>'''
    return text.encode(encoding)


def make_fb2(path: Path, *, encoding: str = "utf-8", binary: str | None = None) -> None:
    path.write_bytes(fb2_xml(encoding=encoding, binary=binary))


def make_fb2_zip(path: Path, *, member: str = "book.fb2") -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, fb2_xml())
