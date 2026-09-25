package ru.kixbox.pulse.ui

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.TrendingDown
import androidx.compose.material.icons.outlined.TrendingUp
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.kixbox.pulse.data.Cell
import ru.kixbox.pulse.data.KpiItem
import ru.kixbox.pulse.data.Widget
import kotlin.math.abs

@Composable
fun WidgetView(w: Widget) {
    when (w) {
        is Widget.Hero -> HeroView(w)
        is Widget.Kpis -> KpiGrid(w)
        is Widget.Chart -> Card(w.title, w.subtitle, w.note) { ChartView(w) }
        is Widget.Table -> Card(w.title, w.subtitle, w.note, padded = false) { TableView(w) }
        is Widget.Share -> Card(w.title, w.subtitle) { ShareView(w) }
        is Widget.Heatmap -> Card(w.title, w.subtitle, w.note) { HeatmapView(w) }
        is Widget.Funnel -> Card(w.title, w.subtitle, w.note) { FunnelView(w) }
        is Widget.Insights -> InsightsView(w)
        is Widget.Note -> NoteView(w)
        is Widget.Header -> Column(Modifier.padding(top = 10.dp, start = 4.dp)) {
            Text(w.title, color = P.ink, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            w.subtitle?.let { Text(it, color = P.muted, fontSize = 12.sp) }
        }
        is Widget.Unknown -> Unit
    }
}

@Composable
fun Card(
    title: String?, subtitle: String? = null, note: String? = null, padded: Boolean = true,
    content: @Composable () -> Unit
) {
    Surface(shape = RoundedCornerShape(20.dp), color = P.card, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(vertical = 16.dp)) {
            Column(Modifier.padding(horizontal = 16.dp)) {
                if (title != null) Text(title, color = P.ink, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                if (subtitle != null) Text(subtitle, color = P.muted, fontSize = 12.sp, lineHeight = 15.sp)
                if (title != null || subtitle != null) Spacer(Modifier.height(10.dp))
            }
            Box(if (padded) Modifier.padding(horizontal = 16.dp) else Modifier) { content() }
            if (note != null) {
                Spacer(Modifier.height(10.dp))
                Text(note, color = P.faint, fontSize = 11.sp, lineHeight = 14.sp,
                    modifier = Modifier.padding(horizontal = 16.dp))
            }
        }
    }
}

// ---------- KPI ----------

@Composable
fun KpiGrid(w: Widget.Kpis) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (w.title != null) {
            Column(Modifier.padding(start = 4.dp, top = 6.dp)) {
                Text(w.title, color = P.ink, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                if (w.subtitle != null) Text(w.subtitle, color = P.muted, fontSize = 12.sp)
            }
        }
        val cols = w.columns.coerceIn(1, 3)
        w.items.chunked(cols).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.height(IntrinsicSize.Min)) {
                row.forEach { KpiCard(it, Modifier.weight(1f).fillMaxHeight()) }
                repeat(cols - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun KpiCard(k: KpiItem, modifier: Modifier = Modifier) {
    var open by remember(k.label) { mutableStateOf(false) }
    Surface(
        shape = RoundedCornerShape(18.dp), color = P.card,
        modifier = modifier.clip(RoundedCornerShape(18.dp)).clickable(enabled = k.hint != null) { open = !open }
    ) {
        Column(Modifier.padding(14.dp).animateContentSize()) {
            Row(verticalAlignment = Alignment.Top) {
                Text(k.label, color = P.muted, fontSize = 12.sp, lineHeight = 14.sp, maxLines = 2,
                    overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                if (k.hint != null) Icon(Icons.Outlined.Info, null, tint = P.faint, modifier = Modifier.size(14.dp))
            }
            Spacer(Modifier.height(4.dp))
            Text(formatValue(k.value, k.format), color = P.ink, fontSize = 21.sp, fontWeight = FontWeight.Bold,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (k.delta != null || k.deltaLy != null) {
                Spacer(Modifier.height(4.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    DeltaChip(k.delta, k.deltaKind, k.better, null)
                    DeltaChip(k.deltaLy, k.deltaKind, k.better, "год")
                }
            }
            if (k.spark.size > 2) {
                Spacer(Modifier.height(8.dp))
                Sparkline(k.spark, P.accent, Modifier.fillMaxWidth().height(26.dp))
            }
            if (open && k.hint != null) {
                Spacer(Modifier.height(6.dp))
                Text(k.hint, color = P.muted, fontSize = 11.sp, lineHeight = 14.sp)
            }
        }
    }
}

fun deltaColor(p: Palette, d: Double?, better: String?): Color {
    if (d == null || abs(d) < 0.0005 || better == null || better == "none") return p.muted
    val good = if (better == "down") d < 0 else d > 0
    return if (good) p.good else p.bad
}

@Composable
fun DeltaChip(d: Double?, kind: String, better: String, prefix: String?) {
    if (d == null) return
    val c = deltaColor(P, d, better)
    val arrow = if (d > 0.0005) "▲" else if (d < -0.0005) "▼" else "•"
    Text(
        (if (prefix != null) "$prefix " else "") + arrow + " " + deltaText(abs(d), kind).removePrefix("+"),
        color = c, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, softWrap = false,
        modifier = Modifier.background(c.copy(alpha = 0.10f), RoundedCornerShape(6.dp)).padding(horizontal = 5.dp, vertical = 1.dp)
    )
}

// ---------- Герой ----------

@Composable
fun HeroView(w: Widget.Hero) {
    val p = P
    Surface(shape = RoundedCornerShape(24.dp), color = p.hero, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(w.title, color = p.heroInk.copy(alpha = .7f), fontSize = 13.sp)
                    Text(formatValue(w.value, w.format), color = p.heroInk, fontSize = 34.sp, fontWeight = FontWeight.Bold)
                    w.subtitle?.let { Text(it, color = p.heroInk.copy(alpha = .7f), fontSize = 12.sp, lineHeight = 15.sp) }
                }
                w.badge?.let {
                    val c = when (it.tone) { "good" -> Color(0xFF34D399); "bad" -> Color(0xFFF87171); else -> Color(0xFFFBBF24) }
                    Text(it.text, color = c, fontSize = 11.sp, fontWeight = FontWeight.Bold,
                        modifier = Modifier.background(c.copy(alpha = .15f), RoundedCornerShape(8.dp))
                            .padding(horizontal = 8.dp, vertical = 4.dp))
                }
            }
            w.progress?.let { prog ->
                BoxWithConstraints(Modifier.fillMaxWidth().height(12.dp)) {
                    val full = maxWidth
                    Box(Modifier.fillMaxWidth().height(8.dp).align(Alignment.Center)
                        .background(p.heroInk.copy(alpha = .14f), RoundedCornerShape(4.dp)))
                    Box(Modifier.width(full * prog.toFloat().coerceIn(0f, 1f)).height(8.dp).align(Alignment.CenterStart)
                        .background(if (prog >= (w.marker ?: 0.0)) Color(0xFF34D399) else p.accent, RoundedCornerShape(4.dp)))
                    w.marker?.let { m ->
                        Box(Modifier.padding(start = full * m.toFloat().coerceIn(0f, 1f)).width(2.dp).fillMaxHeight()
                            .background(p.heroInk.copy(alpha = .85f)))
                    }
                }
                Row {
                    Text("Выполнено ${pct(prog)}", color = p.heroInk.copy(alpha = .7f), fontSize = 11.sp, modifier = Modifier.weight(1f))
                    w.marker?.let { Text("Прошло месяца ${pct(it)}", color = p.heroInk.copy(alpha = .5f), fontSize = 11.sp) }
                }
            }
            if (w.items.isNotEmpty()) {
                Box(Modifier.fillMaxWidth().height(1.dp).background(p.heroInk.copy(alpha = .12f)))
                w.items.chunked(2).forEach { row ->
                    Row {
                        row.forEach { it ->
                            Column(Modifier.weight(1f)) {
                                Text(it.label, color = p.heroInk.copy(alpha = .6f), fontSize = 11.sp)
                                Text(formatValue(it.value, it.format) + (it.suffix ?: ""), color = p.heroInk,
                                    fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                            }
                        }
                        if (row.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

// ---------- Таблица ----------

@Composable
fun TableView(w: Widget.Table) {
    val p = P
    var sortCol by rememberSaveable(w.title) { mutableStateOf(-1) }
    var asc by rememberSaveable(w.title) { mutableStateOf(false) }
    var expanded by rememberSaveable(w.title) { mutableStateOf(false) }
    val rows = remember(w, sortCol, asc) {
        if (sortCol < 0) w.rows else {
            val cmp = compareBy<List<Cell>> { r ->
                val c = r.getOrNull(sortCol)
                c?.number ?: if (w.columns[sortCol].format == "text") null else Double.NEGATIVE_INFINITY
            }.thenBy { it.getOrNull(sortCol)?.text ?: "" }
            if (asc) w.rows.sortedWith(cmp) else w.rows.sortedWith(cmp.reversed())
        }
    }
    val shown = if (expanded || rows.size <= w.collapsed + 2) rows else rows.take(w.collapsed)
    val maxAbs = w.columns.indices.associateWith { j ->
        if (w.columns[j].bar) rows.maxOfOrNull { abs(it.getOrNull(j)?.number ?: 0.0) } ?: 1.0 else 1.0
    }
    val first = w.columns.firstOrNull() ?: return
    val firstW: Dp = (120 * (first.width ?: 1.0)).coerceIn(110.0, 230.0).dp
    val rowH = 40.dp
    val headH = 34.dp
    val scroll = rememberScrollState()

    fun onHeader(j: Int) {
        if (!w.sortable) return
        if (sortCol == j) asc = !asc else { sortCol = j; asc = w.columns[j].format == "text" }
    }

    Column {
        if (w.rows.isEmpty()) {
            Text("Нет данных за период", color = p.muted, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 16.dp))
            return@Column
        }
        Row {
            Column(Modifier.width(firstW + 16.dp).padding(start = 16.dp)) {
                HeaderCell(first.title, TextAlign.Start, sortCol == 0, asc, Modifier.height(headH).fillMaxWidth()) { onHeader(0) }
                shown.forEachIndexed { i, r ->
                    Box(Modifier.height(rowH).fillMaxWidth(), contentAlignment = Alignment.CenterStart) {
                        Text(r.getOrNull(0)?.text ?: formatValue(r.getOrNull(0)?.number, first.format),
                            color = p.ink, fontSize = 13.sp, maxLines = 2, lineHeight = 15.sp,
                            overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
                    }
                    if (i < shown.size - 1) Box(Modifier.fillMaxWidth().height(1.dp).background(p.line))
                }
            }
            Box(Modifier.weight(1f)) {
            Row(Modifier.horizontalScroll(scroll).padding(end = 16.dp)) {
                w.columns.drop(1).forEachIndexed { jj, c ->
                    val j = jj + 1
                    val cw = when {
                        c.format == "text" -> (110 * (c.width ?: 1.0)).dp
                        c.bar -> 92.dp
                        else -> (80 * (c.width ?: 1.0)).dp
                    }
                    Column(Modifier.width(cw)) {
                        HeaderCell(c.title, if (c.format == "text") TextAlign.Start else TextAlign.End,
                            sortCol == j, asc, Modifier.height(headH).fillMaxWidth().padding(start = 6.dp)) { onHeader(j) }
                        shown.forEachIndexed { i, r ->
                            Box(Modifier.height(rowH).fillMaxWidth().padding(start = 6.dp),
                                contentAlignment = if (c.format == "text") Alignment.CenterStart else Alignment.CenterEnd) {
                                TableCell(r.getOrNull(j), c, maxAbs[j] ?: 1.0)
                            }
                            if (i < shown.size - 1) Box(Modifier.fillMaxWidth().height(1.dp).background(p.line))
                        }
                    }
                }
            }
            if (scroll.maxValue > 0 && scroll.value < scroll.maxValue) {
                Box(Modifier.matchParentSize()) {
                    Box(Modifier.align(Alignment.CenterEnd).width(28.dp).fillMaxHeight()
                        .background(Brush.horizontalGradient(listOf(p.card.copy(alpha = 0f), p.card))))
                }
            }
            }
        }
        if (rows.size > shown.size || (expanded && rows.size > w.collapsed + 2)) {
            Text(
                if (expanded) "Свернуть" else "Показать все · ${rows.size}",
                color = p.accent, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(start = 16.dp, top = 8.dp).clickable { expanded = !expanded }
            )
        }
    }
}

@Composable
private fun HeaderCell(title: String, align: TextAlign, active: Boolean, asc: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Box(modifier.clickable(onClick = onClick), contentAlignment = if (align == TextAlign.Start) Alignment.CenterStart else Alignment.CenterEnd) {
        Text(
            title + if (active) (if (asc) " ↑" else " ↓") else "",
            color = if (active) P.accent else P.muted, fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
            maxLines = 2, lineHeight = 12.sp, textAlign = align
        )
    }
}

@Composable
private fun TableCell(cell: Cell?, c: ru.kixbox.pulse.data.Column, maxAbs: Double) {
    val p = P
    if (cell == null || (cell.number == null && cell.text == null)) {
        Text("—", color = p.faint, fontSize = 13.sp)
        return
    }
    if (c.format == "text") {
        Text(cell.text ?: "", color = p.ink, fontSize = 12.sp, maxLines = 2, lineHeight = 14.sp, overflow = TextOverflow.Ellipsis)
        return
    }
    val v = cell.number
    if (c.delta) {
        val col = deltaColor(p, v, c.better ?: "up")
        Text(deltaText(v, "rel").ifEmpty { "—" }, color = col, fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold)
        return
    }
    val txt = formatValue(v, c.format).replace(" ₽", "")
    if (c.bar && v != null) {
        Box(Modifier.fillMaxWidth().height(22.dp), contentAlignment = Alignment.CenterEnd) {
            Box(Modifier.fillMaxWidth((abs(v) / maxAbs).toFloat().coerceIn(0.02f, 1f)).fillMaxHeight().align(Alignment.CenterStart)
                .background(p.accent.copy(alpha = .16f), RoundedCornerShape(4.dp)))
            Text(txt, color = p.ink, fontSize = 12.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(end = 4.dp))
        }
        return
    }
    Text(txt, color = p.ink, fontSize = 13.sp, maxLines = 1)
}

// ---------- Выводы и заметки ----------

@Composable
fun InsightsView(w: Widget.Insights) {
    val p = P
    Surface(shape = RoundedCornerShape(20.dp), color = p.card, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(w.title, color = p.ink, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            w.items.forEach { it ->
                val c = p.tone(it.tone)
                val icon = when (it.tone) {
                    "good" -> Icons.Outlined.TrendingUp
                    "bad" -> Icons.Outlined.TrendingDown
                    "warn" -> Icons.Outlined.WarningAmber
                    else -> Icons.Outlined.Info
                }
                Row(verticalAlignment = Alignment.Top) {
                    Box(Modifier.size(26.dp).background(c.copy(alpha = .12f), RoundedCornerShape(8.dp)),
                        contentAlignment = Alignment.Center) {
                        Icon(icon, null, tint = c, modifier = Modifier.size(16.dp))
                    }
                    Spacer(Modifier.width(10.dp))
                    Text(it.text, color = p.ink, fontSize = 14.sp, lineHeight = 19.sp, modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
fun NoteView(w: Widget.Note) {
    val p = P
    var open by rememberSaveable(w.text) { mutableStateOf(false) }
    Surface(shape = RoundedCornerShape(16.dp), color = p.cardAlt, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.clickable { open = !open }.padding(14.dp).animateContentSize()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(if (w.title == "Раздел не собрался") Icons.Outlined.ErrorOutline else Icons.Outlined.Info, null,
                    tint = p.muted, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(8.dp))
                Text(w.title ?: "Примечание", color = p.muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f))
                Icon(if (open) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, null, tint = p.muted)
            }
            if (open || w.title == "Раздел не собрался") {
                Spacer(Modifier.height(6.dp))
                Text(w.text, color = p.muted, fontSize = 12.sp, lineHeight = 16.sp)
            }
        }
    }
}
