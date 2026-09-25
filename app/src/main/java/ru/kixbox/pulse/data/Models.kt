package ru.kixbox.pulse.data

import org.json.JSONArray
import org.json.JSONObject

/** Описание раздела, которое присылает сервер. Приложение только рисует виджеты. */
data class SectionInfo(val id: String, val title: String, val icon: String)
data class PeriodInfo(val id: String, val title: String)
data class SourceInfo(val id: String, val name: String, val last: String?, val ok: Boolean)

data class Freshness(
    val end: String?,
    val c1Complete: String?,
    val checkedAt: String?,
    val sources: List<SourceInfo>
)

data class Meta(
    val sections: List<SectionInfo>,
    val periods: List<PeriodInfo>,
    val freshness: Freshness
)

data class PeriodLabel(
    val preset: String,
    val title: String,
    val label: String,
    val prevLabel: String,
    val lyLabel: String,
    val prevName: String,
    val bucket: String
)

data class SectionPayload(
    val id: String,
    val title: String,
    val period: PeriodLabel,
    val widgets: List<Widget>,
    val generatedAt: String,
    val dataEnd: String,
    val error: String?
)

sealed interface Widget {
    data class Kpis(val title: String?, val subtitle: String?, val items: List<KpiItem>, val columns: Int) : Widget
    data class Hero(
        val title: String, val value: Double?, val format: String, val subtitle: String?,
        val progress: Double?, val marker: Double?, val items: List<HeroItem>, val badge: Badge?
    ) : Widget
    data class Chart(
        val title: String, val subtitle: String?, val kind: String, val stacked: Boolean,
        val x: List<String>, val series: List<Series>, val note: String?
    ) : Widget
    data class Table(
        val title: String, val subtitle: String?, val columns: List<Column>, val rows: List<List<Cell>>,
        val collapsed: Int, val sortable: Boolean, val note: String?
    ) : Widget
    data class Share(val title: String, val subtitle: String?, val format: String, val total: Double,
                     val items: List<ShareItem>) : Widget
    data class Heatmap(val title: String, val subtitle: String?, val x: List<String>, val y: List<String>,
                       val values: List<List<Double?>>, val format: String, val note: String?) : Widget
    data class Funnel(val title: String, val subtitle: String?, val steps: List<Pair<String, Double?>>,
                      val note: String?) : Widget
    data class Insights(val title: String, val items: List<Insight>) : Widget
    data class Note(val title: String?, val text: String) : Widget
    data class Header(val title: String, val subtitle: String?) : Widget
    data class Unknown(val type: String) : Widget
}

data class KpiItem(
    val label: String, val value: Double?, val format: String, val delta: Double?, val deltaLy: Double?,
    val deltaKind: String, val better: String, val hint: String?, val spark: List<Double>
)

data class HeroItem(val label: String, val value: Double?, val format: String, val suffix: String?)
data class Badge(val text: String, val tone: String)
data class Series(val name: String, val values: List<Double?>, val format: String, val style: String,
                  val axis: String, val color: Int?)

data class Column(val title: String, val format: String, val bar: Boolean, val better: String?,
                  val delta: Boolean, val align: String, val width: Double?)

/** Ячейка таблицы: либо текст, либо число. */
data class Cell(val text: String?, val number: Double?)

data class ShareItem(val label: String, val value: Double, val share: Double)
data class Insight(val tone: String, val text: String)

// ---------- разбор JSON ----------

private fun JSONObject.str(name: String): String? =
    if (!has(name) || isNull(name)) null else optString(name)

private fun JSONObject.dbl(name: String): Double? =
    if (!has(name) || isNull(name)) null else optDouble(name).takeUnless { it.isNaN() }

private fun JSONArray?.objects(): List<JSONObject> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

private fun JSONArray?.strings(): List<String> =
    if (this == null) emptyList() else (0 until length()).map { optString(it) }

private fun JSONArray?.doubles(): List<Double?> =
    if (this == null) emptyList()
    else (0 until length()).map { if (isNull(it)) null else optDouble(it).takeUnless { d -> d.isNaN() } }

fun parseMeta(raw: String): Meta {
    val o = JSONObject(raw)
    val f = o.optJSONObject("freshness") ?: JSONObject()
    return Meta(
        sections = o.optJSONArray("sections").objects().map {
            SectionInfo(it.optString("id"), it.optString("title"), it.optString("icon"))
        },
        periods = o.optJSONArray("periods").objects().map { PeriodInfo(it.optString("id"), it.optString("title")) },
        freshness = parseFreshness(f)
    )
}

fun parseFreshness(f: JSONObject) = Freshness(
    end = f.str("end"),
    c1Complete = f.str("c1_complete"),
    checkedAt = f.str("checked_at"),
    sources = f.optJSONArray("sources").objects().map {
        SourceInfo(it.optString("id"), it.optString("name"), it.str("last"), it.optBoolean("ok", true))
    }
)

fun parseSection(raw: String): SectionPayload {
    val o = JSONObject(raw)
    val p = o.optJSONObject("period") ?: JSONObject()
    return SectionPayload(
        id = o.optString("id"),
        title = o.optString("title"),
        period = PeriodLabel(
            preset = p.optString("preset"), title = p.optString("title"), label = p.optString("label"),
            prevLabel = p.optString("prev_label"), lyLabel = p.optString("ly_label"),
            prevName = p.optString("prev_name"), bucket = p.optString("bucket")
        ),
        widgets = o.optJSONArray("widgets").objects().map(::parseWidget),
        generatedAt = o.optString("generated_at"),
        dataEnd = o.optString("data_end"),
        error = o.str("error")
    )
}

fun parseWidget(w: JSONObject): Widget = when (w.optString("type")) {
    "kpis" -> Widget.Kpis(
        title = w.str("title"), subtitle = w.str("subtitle"), columns = w.optInt("columns", 2),
        items = w.optJSONArray("items").objects().map {
            KpiItem(
                label = it.optString("label"), value = it.dbl("value"), format = it.optString("format", "int"),
                delta = it.dbl("delta"), deltaLy = it.dbl("delta_ly"), deltaKind = it.optString("delta_kind", "rel"),
                better = it.optString("better", "up"), hint = it.str("hint"),
                spark = it.optJSONArray("spark").doubles().map { d -> d ?: 0.0 }
            )
        }
    )
    "hero" -> Widget.Hero(
        title = w.optString("title"), value = w.dbl("value"), format = w.optString("format", "money"),
        subtitle = w.str("subtitle"), progress = w.dbl("progress"), marker = w.dbl("marker"),
        items = w.optJSONArray("items").objects().map {
            HeroItem(it.optString("label"), it.dbl("value"), it.optString("format", "money"), it.str("suffix"))
        },
        badge = w.optJSONObject("badge")?.let { Badge(it.optString("text"), it.optString("tone")) }
    )
    "chart" -> Widget.Chart(
        title = w.optString("title"), subtitle = w.str("subtitle"), kind = w.optString("kind", "bar"),
        stacked = w.optBoolean("stacked", false), x = w.optJSONArray("x").strings(), note = w.str("note"),
        series = w.optJSONArray("series").objects().map {
            Series(
                name = it.optString("name"), values = it.optJSONArray("values").doubles(),
                format = it.optString("format", "money"), style = it.optString("style", "bar"),
                axis = it.optString("axis", "left"), color = if (it.has("color")) it.optInt("color") else null
            )
        }
    )
    "table" -> {
        val cols = w.optJSONArray("columns").objects().map {
            Column(
                title = it.optString("title"), format = it.optString("format", "text"),
                bar = it.optBoolean("bar", false), better = it.str("better"), delta = it.optBoolean("delta", false),
                align = it.optString("align", "end"), width = it.dbl("width")
            )
        }
        val rows = w.optJSONArray("rows")
        Widget.Table(
            title = w.optString("title"), subtitle = w.str("subtitle"), columns = cols,
            collapsed = w.optInt("collapsed", 10), sortable = w.optBoolean("sortable", true), note = w.str("note"),
            rows = if (rows == null) emptyList() else (0 until rows.length()).map { i ->
                val r = rows.optJSONArray(i) ?: JSONArray()
                (0 until r.length()).map { j ->
                    when {
                        r.isNull(j) -> Cell(null, null)
                        cols.getOrNull(j)?.format == "text" -> Cell(r.opt(j)?.toString(), null)
                        else -> {
                            val v = r.opt(j)
                            if (v is Number) Cell(null, v.toDouble()) else Cell(v?.toString(), v?.toString()?.toDoubleOrNull())
                        }
                    }
                }
            }
        )
    }
    "share" -> Widget.Share(
        title = w.optString("title"), subtitle = w.str("subtitle"), format = w.optString("format", "money"),
        total = w.optDouble("total", 0.0),
        items = w.optJSONArray("items").objects().map {
            ShareItem(it.optString("label"), it.optDouble("value", 0.0), it.optDouble("share", 0.0))
        }
    )
    "heatmap" -> Widget.Heatmap(
        title = w.optString("title"), subtitle = w.str("subtitle"), x = w.optJSONArray("x").strings(),
        y = w.optJSONArray("y").strings(), format = w.optString("format", "int"), note = w.str("note"),
        values = w.optJSONArray("values").let { arr ->
            if (arr == null) emptyList() else (0 until arr.length()).map { arr.optJSONArray(it).doubles() }
        }
    )
    "funnel" -> Widget.Funnel(
        title = w.optString("title"), subtitle = w.str("subtitle"), note = w.str("note"),
        steps = w.optJSONArray("steps").objects().map { it.optString("label") to it.dbl("value") }
    )
    "insights" -> Widget.Insights(
        title = w.optString("title"),
        items = w.optJSONArray("items").objects().map { Insight(it.optString("tone"), it.optString("text")) }
    )
    "note" -> Widget.Note(w.str("title"), w.optString("text"))
    "header" -> Widget.Header(w.optString("title"), w.str("subtitle"))
    else -> Widget.Unknown(w.optString("type"))
}
