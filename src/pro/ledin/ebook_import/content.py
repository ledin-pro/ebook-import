from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Literal, Sequence, TypeAlias


@dataclass(frozen=True)
class Text:
    value: str


@dataclass(frozen=True)
class Emphasis:
    children: tuple[Inline, ...]


@dataclass(frozen=True)
class Strong:
    children: tuple[Inline, ...]


@dataclass(frozen=True)
class Strike:
    children: tuple[Inline, ...]


@dataclass(frozen=True)
class InlineCode:
    value: str


@dataclass(frozen=True)
class Subscript:
    children: tuple[Inline, ...]


@dataclass(frozen=True)
class Superscript:
    children: tuple[Inline, ...]


@dataclass(frozen=True)
class Link:
    children: tuple[Inline, ...]
    href: str


@dataclass(frozen=True)
class FootnoteRef:
    note_id: str
    label: str


@dataclass(frozen=True)
class ImageInline:
    source_id: str
    filename: str
    alt: str = ""
    caption: tuple[Inline, ...] = ()
    role: Literal["content", "cover"] = "content"


@dataclass(frozen=True)
class HardBreak:
    pass


Inline: TypeAlias = Text | Emphasis | Strong | Strike | InlineCode | Subscript | Superscript | Link | FootnoteRef | ImageInline | HardBreak


@dataclass(frozen=True)
class Heading:
    level: int
    children: tuple[Inline, ...]


@dataclass(frozen=True)
class Paragraph:
    children: tuple[Inline, ...]


@dataclass(frozen=True)
class Quote:
    children: tuple[Block, ...]
    kind: Literal["blockquote", "epigraph", "cite"] = "blockquote"
    attribution: tuple[Inline, ...] = ()


@dataclass(frozen=True)
class Verse:
    children: tuple[Inline, ...]


@dataclass(frozen=True)
class Stanza:
    verses: tuple[Verse, ...]


@dataclass(frozen=True)
class Poem:
    title: tuple[Inline, ...] = ()
    stanzas: tuple[Stanza, ...] = ()
    attribution: tuple[Inline, ...] = ()
    heading_level: int = 2


@dataclass(frozen=True)
class TableCell:
    children: tuple[Inline, ...]
    header: bool = False
    rowspan: int = 1
    colspan: int = 1


@dataclass(frozen=True)
class TableRow:
    cells: tuple[TableCell, ...]


@dataclass(frozen=True)
class Table:
    rows: tuple[TableRow, ...]


@dataclass(frozen=True)
class ImageBlock:
    image: ImageInline


@dataclass(frozen=True)
class CodeBlock:
    value: str
    language: str = ""


@dataclass(frozen=True)
class FootnoteDefinition:
    note_id: str
    label: str
    children: tuple[Block, ...]


@dataclass(frozen=True)
class EmptyLine:
    pass


@dataclass(frozen=True)
class ListItem:
    children: tuple[Inline, ...]


@dataclass(frozen=True)
class ListBlock:
    items: tuple[ListItem, ...]
    ordered: bool = False


@dataclass(frozen=True)
class Group:
    kind: Literal["document", "body", "chapter", "section"]
    children: tuple[Block, ...]
    title: tuple[Inline, ...] = ()
    heading_level: int = 2


Block: TypeAlias = Heading | Paragraph | Quote | Poem | Table | ImageBlock | CodeBlock | FootnoteDefinition | EmptyLine | ListBlock | Group


def inline_text(nodes: Sequence[Inline]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, Text):
            parts.append(node.value)
        elif isinstance(node, InlineCode):
            parts.append(node.value)
        elif isinstance(node, (Emphasis, Strong, Strike, Subscript, Superscript, Link)):
            parts.append(inline_text(node.children))
        elif isinstance(node, FootnoteRef):
            parts.append(node.label)
        elif isinstance(node, ImageInline):
            parts.append(node.alt)
        elif isinstance(node, HardBreak):
            parts.append("\n")
    return "".join(parts)


def render_inline(nodes: Sequence[Inline]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, Text):
            parts.append(node.value)
        elif isinstance(node, Emphasis):
            parts.append(f"*{render_inline(node.children).strip()}*")
        elif isinstance(node, Strong):
            parts.append(f"**{render_inline(node.children).strip()}**")
        elif isinstance(node, Strike):
            parts.append(f"~~{render_inline(node.children).strip()}~~")
        elif isinstance(node, InlineCode):
            parts.append(f"`{node.value.strip()}`")
        elif isinstance(node, Subscript):
            parts.append(f"<sub>{render_inline(node.children).strip()}</sub>")
        elif isinstance(node, Superscript):
            parts.append(f"<sup>{render_inline(node.children).strip()}</sup>")
        elif isinstance(node, Link):
            label = render_inline(node.children).strip()
            parts.append(f"[{label}]({node.href})" if node.href else label)
        elif isinstance(node, FootnoteRef):
            parts.append(f"[^{node.label}]")
        elif isinstance(node, ImageInline):
            parts.append(f"![{node.alt}](../media/{node.filename})")
        elif isinstance(node, HardBreak):
            parts.append("  \n")
    text = "".join(parts)
    return text


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _table_html(table: Table) -> str:
    lines = ["<table>"]
    for row in table.rows:
        lines.append("  <tr>")
        for cell in row.cells:
            tag = "th" if cell.header else "td"
            attrs = ""
            if cell.rowspan > 1:
                attrs += f' rowspan="{cell.rowspan}"'
            if cell.colspan > 1:
                attrs += f' colspan="{cell.colspan}"'
            lines.append(f"    <{tag}{attrs}>{html.escape(render_inline(cell.children).strip())}</{tag}>")
        lines.append("  </tr>")
    lines.append("</table>")
    return "\n".join(lines)


def render_block(block: Block) -> str:
    if isinstance(block, Heading):
        return f"{'#' * max(1, min(block.level, 6))} {render_inline(block.children).strip()}"
    if isinstance(block, Paragraph):
        return render_inline(block.children).strip()
    if isinstance(block, Quote):
        content = render_markdown(block.children).strip()
        if block.attribution:
            content = f"{content}\n\n{render_inline(block.attribution).strip()}"
        return _quote(content)
    if isinstance(block, Poem):
        parts: list[str] = []
        if block.title:
            parts.append(f"{'#' * max(1, min(block.heading_level, 6))} {render_inline(block.title).strip()}")
        for stanza in block.stanzas:
            parts.append("  \n".join(render_inline(verse.children).strip() for verse in stanza.verses))
        if block.attribution:
            parts.append(_quote(render_inline(block.attribution).strip()))
        return "\n\n".join(part for part in parts if part)
    if isinstance(block, Table):
        if not block.rows:
            return ""
        width = len(block.rows[0].cells)
        simple = width > 0 and all(len(row.cells) == width for row in block.rows) and all(cell.rowspan == 1 and cell.colspan == 1 for row in block.rows for cell in row.cells)
        if not simple:
            return _table_html(block)
        rows = [[render_inline(cell.children).strip() for cell in row.cells] for row in block.rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join("---" for _ in rows[0]) + " |"]
        lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
        return "\n".join(lines)
    if isinstance(block, ImageBlock):
        return render_inline((block.image,))
    if isinstance(block, CodeBlock):
        return f"```{block.language}\n{block.value.rstrip()}\n```"
    if isinstance(block, FootnoteDefinition):
        content = render_markdown(block.children).strip()
        lines = content.splitlines() or [""]
        return f"[^{block.label}]: {lines[0]}" + "".join(f"\n    {line}" for line in lines[1:])
    if isinstance(block, EmptyLine):
        return ""
    if isinstance(block, ListBlock):
        lines = []
        for index, item in enumerate(block.items, start=1):
            marker = f"{index}." if block.ordered else "-"
            lines.append(f"{marker} {render_inline(item.children).strip()}")
        return "\n".join(lines)
    if isinstance(block, Group):
        parts: list[str] = []
        if block.title:
            parts.append(f"{'#' * max(1, min(block.heading_level, 6))} {render_inline(block.title).strip()}")
        content = render_markdown(block.children).strip()
        if content:
            parts.append(content)
        return "\n\n".join(parts)
    raise TypeError(f"Unsupported block: {type(block)!r}")


def render_markdown(blocks: Sequence[Block]) -> str:
    parts = [render_block(block) for block in blocks]
    output: list[str] = []
    for part in parts:
        if part == "":
            if output and output[-1] != "":
                output.append("")
            continue
        output.append(part.strip())
    return "\n\n".join(output).strip() + ("\n" if output else "")


def parse_inline_markdown(value: str) -> tuple[Inline, ...]:
    nodes: list[Inline] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            nodes.append(Text("".join(buffer)))
            buffer.clear()

    index = 0
    while index < len(value):
        if value.startswith("![", index):
            match = re.match(r"!\[([^\]]*)\]\(\.\./media/([^)]+)\)", value[index:])
            if match:
                flush()
                nodes.append(ImageInline(match.group(2), match.group(2), match.group(1)))
                index += match.end()
                continue
        if value.startswith("**", index):
            end = value.find("**", index + 2)
            if end >= 0:
                flush()
                nodes.append(Strong(parse_inline_markdown(value[index + 2:end])))
                index = end + 2
                continue
        if value.startswith("~~", index):
            end = value.find("~~", index + 2)
            if end >= 0:
                flush()
                nodes.append(Strike(parse_inline_markdown(value[index + 2:end])))
                index = end + 2
                continue
        if value[index] == "*":
            end = value.find("*", index + 1)
            if end >= 0:
                flush()
                nodes.append(Emphasis(parse_inline_markdown(value[index + 1:end])))
                index = end + 1
                continue
        if value[index] == "`":
            end = value.find("`", index + 1)
            if end >= 0:
                flush()
                nodes.append(InlineCode(value[index + 1:end]))
                index = end + 1
                continue
        if value[index] == "[":
            match = re.match(r"\[([^\]]+)\]\(([^)]*)\)", value[index:])
            if match:
                flush()
                nodes.append(Link(parse_inline_markdown(match.group(1)), match.group(2)))
                index += match.end()
                continue
        if value.startswith("  \n", index):
            flush()
            nodes.append(HardBreak())
            index += 3
            continue
        buffer.append(value[index])
        index += 1
    flush()
    return tuple(nodes)


def parse_markdown_blocks(markdown: str) -> tuple[Block, ...]:
    lines = markdown.strip().splitlines()
    blocks: list[Block] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            blocks.append(Heading(len(heading.group(1)), parse_inline_markdown(heading.group(2))))
            index += 1
            continue
        if line.startswith(">"):
            quoted: list[str] = []
            while index < len(lines) and lines[index].startswith(">"):
                quoted.append(lines[index][1:].lstrip())
                index += 1
            blocks.append(Quote((Paragraph(parse_inline_markdown("\n".join(quoted))),)))
            continue
        if re.match(r"^(?:- |\d+\. )", line):
            ordered = bool(re.match(r"^\d+\. ", line))
            items: list[ListItem] = []
            pattern = r"^\d+\.\s+" if ordered else r"^-\s+"
            while index < len(lines) and re.match(pattern, lines[index]):
                items.append(ListItem(parse_inline_markdown(re.sub(pattern, "", lines[index]))))
                index += 1
            blocks.append(ListBlock(tuple(items), ordered))
            continue
        if line.startswith("```"):
            language = line[3:].strip()
            code: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index])
                index += 1
            index += 1
            blocks.append(CodeBlock("\n".join(code), language))
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(?:#{1,6}\s+|> |-|\d+\. |```)", lines[index]):
            paragraph.append(lines[index])
            index += 1
        paragraph_nodes = parse_inline_markdown("\n".join(paragraph))
        if len(paragraph_nodes) == 1 and isinstance(paragraph_nodes[0], ImageInline):
            blocks.append(ImageBlock(paragraph_nodes[0]))
        else:
            blocks.append(Paragraph(paragraph_nodes))
    return tuple(blocks)
