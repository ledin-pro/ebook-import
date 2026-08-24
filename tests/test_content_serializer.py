from __future__ import annotations

from pro.ledin.ebook_import.content import (
    CodeBlock,
    Emphasis,
    EmptyLine,
    FootnoteDefinition,
    FootnoteRef,
    Group,
    HardBreak,
    Heading,
    ImageBlock,
    ImageInline,
    InlineCode,
    Link,
    ListBlock,
    ListItem,
    Paragraph,
    Poem,
    Quote,
    Stanza,
    Strike,
    Strong,
    Subscript,
    Superscript,
    Table,
    TableCell,
    TableRow,
    Text,
    Verse,
    inline_text,
    parse_inline_markdown,
    parse_markdown_blocks,
    render_markdown,
)


def test_all_inline_nodes_render_and_flatten() -> None:
    nodes = (
        Text("A "),
        Strong((Text("bold"),)),
        Text(" "),
        Emphasis((Text("italic"),)),
        Strike((Text("strike"),)),
        InlineCode("code"),
        Subscript((Text("sub"),)),
        Superscript((Text("sup"),)),
        Link((Text("link"),), "https://example.com"),
        FootnoteRef("n", "n"),
        ImageInline("img", "img.png", "alt"),
        HardBreak(),
    )
    text = render_markdown((Paragraph(nodes),))
    assert "**bold**" in text
    assert "*italic*" in text
    assert "~~strike~~" in text
    assert "`code`" in text
    assert "<sub>sub</sub>" in text
    assert "<sup>sup</sup>" in text
    assert "[link](https://example.com)" in text
    assert "[^n]" in text
    assert "![alt](../media/img.png)" in text
    assert inline_text(nodes).startswith("A bold italic")


def test_all_block_nodes_render() -> None:
    simple_table = Table((TableRow((TableCell((Text("A"),), header=True), TableCell((Text("B"),), header=True))), TableRow((TableCell((Text("1"),)), TableCell((Text("2"),))))))
    span_table = Table((TableRow((TableCell((Text("wide"),), colspan=2),)),))
    blocks = (
        Heading(2, (Text("Heading"),)),
        Quote((Paragraph((Text("Quote"),)),), attribution=(Text("Author"),)),
        Poem((Text("Poem"),), (Stanza((Verse((Text("One"),)), Verse((Text("Two"),)))),), (Text("Poet"),), 3),
        simple_table,
        span_table,
        ImageBlock(ImageInline("img", "img.png", "alt")),
        CodeBlock("print('x')", "python"),
        FootnoteDefinition("n", "n", (Paragraph((Text("Note"),)),)),
        ListBlock((ListItem((Text("First"),)), ListItem((Text("Second"),))), ordered=True),
        Group("section", (Paragraph((Text("Body"),)),), (Text("Section"),), 3),
        EmptyLine(),
    )
    text = render_markdown(blocks)
    assert "## Heading" in text
    assert "> Quote" in text and "> Author" in text
    assert "### Poem" in text and "One  \nTwo" in text
    assert "| A | B |" in text
    assert '<td colspan="2">wide</td>' in text
    assert "```python" in text
    assert "[^n]: Note" in text
    assert "1. First" in text
    assert "### Section" in text


def test_generated_markdown_parser_covers_supported_constructs() -> None:
    markdown = """## Heading

> Quote

- One
- Two

1. First
2. Second

```python
print('x')
```

![alt](../media/image.png)

Text with **bold**, *italic*, ~~strike~~, `code`, and [link](target).
next
"""
    blocks = parse_markdown_blocks(markdown)
    assert any(isinstance(block, Heading) for block in blocks)
    assert any(isinstance(block, Quote) for block in blocks)
    assert sum(isinstance(block, ListBlock) for block in blocks) == 2
    assert any(isinstance(block, CodeBlock) for block in blocks)
    assert any(isinstance(block, ImageBlock) for block in blocks)
    parsed = parse_inline_markdown("![a](../media/a.png) **b** *i* ~~s~~ `c` [l](x)  \n")
    assert any(isinstance(node, ImageInline) for node in parsed)
    assert any(isinstance(node, HardBreak) for node in parsed)
