package ru.kixbox.pulse

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Campaign
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.Dashboard
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.Language
import androidx.compose.material.icons.outlined.LocalShipping
import androidx.compose.material.icons.outlined.MailOutline
import androidx.compose.material.icons.outlined.Radar
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Sell
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.ShoppingCart
import androidx.compose.material.icons.outlined.Storefront
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryScrollableTabRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.launch
import ru.kixbox.pulse.data.Freshness
import ru.kixbox.pulse.data.SectionInfo
import ru.kixbox.pulse.ui.P
import ru.kixbox.pulse.ui.PulseTheme
import ru.kixbox.pulse.ui.WidgetView
import ru.kixbox.pulse.ui.shortDate
import ru.kixbox.pulse.ui.timeStamp
import java.time.LocalDate

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent { PulseTheme { PulseApp() } }
    }
}

fun iconFor(name: String): ImageVector = when (name) {
    "dashboard" -> Icons.Outlined.Dashboard
    "cart" -> Icons.Outlined.ShoppingCart
    "tag" -> Icons.Outlined.Sell
    "store" -> Icons.Outlined.Storefront
    "people" -> Icons.Outlined.Groups
    "traffic" -> Icons.Outlined.Language
    "ads" -> Icons.Outlined.Campaign
    "mail" -> Icons.Outlined.MailOutline
    "truck" -> Icons.Outlined.LocalShipping
    "box" -> Icons.Outlined.Inventory2
    "radar" -> Icons.Outlined.Radar
    else -> Icons.Outlined.Dashboard
}

@Composable
fun PulseApp(vm: PulseViewModel = viewModel()) {
    Box(Modifier.fillMaxSize().background(P.bg)) {
        if (!vm.configured) SetupScreen(vm) else MainScreen(vm)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(vm: PulseViewModel) {
    val sections = vm.sections
    val pager = rememberPagerState(initialPage = vm.repo.lastSection.coerceIn(0, sections.size - 1)) { sections.size }
    val scope = rememberCoroutineScope()
    var showSettings by remember { mutableStateOf(false) }
    var showSources by remember { mutableStateOf(false) }

    LaunchedEffect(pager) {
        snapshotFlow { pager.currentPage }.collect { vm.repo.lastSection = it }
    }

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        // Шапка
        Row(Modifier.fillMaxWidth().padding(start = 18.dp, end = 6.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("KIXBOX Pulse", color = P.ink, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                val fresh = vm.meta?.freshness
                val current = sections.getOrNull(pager.currentPage)
                val payload = current?.let { vm.page(it.id).payload }
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { showSources = true }) {
                    val lag = fresh?.let { sourcesLagging(it) } ?: 0
                    Box(Modifier.size(7.dp).background(if (lag == 0) P.good else P.warn, CircleShape))
                    Spacer(Modifier.width(6.dp))
                    Text(
                        (payload?.period?.label ?: "Данные") + " · по ${shortDate(fresh?.end ?: payload?.dataEnd)}",
                        color = P.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                    )
                }
            }
            IconButton(onClick = {
                sections.getOrNull(pager.currentPage)?.let { vm.refreshAll(it.id) }
            }) { Icon(Icons.Outlined.Refresh, "Обновить", tint = P.ink) }
            IconButton(onClick = { showSettings = true }) { Icon(Icons.Outlined.Settings, "Настройки", tint = P.ink) }
        }

        // Разделы
        PrimaryScrollableTabRow(
            selectedTabIndex = pager.currentPage.coerceIn(0, sections.size - 1),
            edgePadding = 12.dp,
            containerColor = P.bg,
            contentColor = P.ink,
            divider = {},
            indicator = {
                TabRowDefaults.PrimaryIndicator(
                    Modifier.tabIndicatorOffset(pager.currentPage.coerceIn(0, sections.size - 1), matchContentSize = true),
                    width = androidx.compose.ui.unit.Dp.Unspecified, color = P.accent
                )
            }
        ) {
            sections.forEachIndexed { i, s ->
                val sel = pager.currentPage == i
                Tab(
                    selected = sel,
                    onClick = { scope.launch { pager.animateScrollToPage(i) } },
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(iconFor(s.icon), null, modifier = Modifier.size(18.dp),
                                tint = if (sel) P.accent else P.muted)
                            Spacer(Modifier.width(6.dp))
                            Text(s.title, color = if (sel) P.ink else P.muted, fontSize = 14.sp,
                                fontWeight = if (sel) FontWeight.Bold else FontWeight.Medium)
                        }
                    }
                )
            }
        }

        // Периоды
        LazyRow(
            contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(vm.periods) { p ->
                val sel = p.id == vm.period
                FilterChip(
                    selected = sel,
                    onClick = { vm.selectPeriod(p.id) },
                    label = { Text(p.title, fontSize = 13.sp) },
                    shape = RoundedCornerShape(12.dp),
                    colors = FilterChipDefaults.filterChipColors(
                        containerColor = P.card, labelColor = P.ink,
                        selectedContainerColor = P.ink, selectedLabelColor = P.bg
                    ),
                    border = null
                )
            }
        }

        HorizontalPager(state = pager, modifier = Modifier.fillMaxSize(), beyondViewportPageCount = 0) { page ->
            val s = sections[page]
            SectionPage(vm, s)
        }
    }

    if (showSettings) SettingsDialog(vm) { showSettings = false }
    if (showSources) vm.meta?.freshness?.let { SourcesDialog(it) { showSources = false } }
}

fun sourcesLagging(f: Freshness): Int {
    val end = f.end?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: return 0
    return f.sources.count { s ->
        val last = s.last?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
        s.id != "stock" && (last == null || last.isBefore(end.minusDays(1)))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SectionPage(vm: PulseViewModel, s: SectionInfo) {
    LaunchedEffect(s.id, vm.period) { vm.ensure(s.id) }
    val st = vm.page(s.id)
    val payload = st.payload
    PullToRefreshBox(
        isRefreshing = st.loading && payload != null,
        onRefresh = { vm.load(s.id, refresh = true) },
        modifier = Modifier.fillMaxSize()
    ) {
        when {
            payload == null && st.loading -> LoadingState(s.title)
            payload == null -> ErrorState(st.error ?: "Нет данных", onRetry = { vm.load(s.id, refresh = false) })
            else -> LazyColumn(
                contentPadding = PaddingValues(start = 14.dp, end = 14.dp, top = 4.dp, bottom = 40.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.fillMaxSize()
            ) {
                item {
                    Column {
                        Text(
                            buildString {
                                append(payload.period.label)
                                if (payload.period.prevName.isNotBlank()) append(" · дельты ${payload.period.prevName}")
                            },
                            color = P.muted, fontSize = 11.sp, lineHeight = 14.sp
                        )
                        if (st.error != null) {
                            Spacer(Modifier.height(6.dp))
                            Row(verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.background(P.warn.copy(alpha = .12f), RoundedCornerShape(10.dp))
                                    .padding(horizontal = 10.dp, vertical = 6.dp)) {
                                Icon(Icons.Outlined.CloudOff, null, tint = P.warn, modifier = Modifier.size(14.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Показаны сохранённые данные: ${st.error}", color = P.warn, fontSize = 11.sp)
                            }
                        } else if (st.fromCache && st.loading) {
                            Text("Обновляю…", color = P.faint, fontSize = 11.sp)
                        }
                    }
                }
                itemsIndexed(payload.widgets, key = { i, _ -> "${s.id}-${vm.period}-$i" }) { _, w -> WidgetView(w) }
                item {
                    Text("Собрано ${timeStamp(payload.generatedAt)}", color = P.faint, fontSize = 11.sp,
                        modifier = Modifier.padding(top = 4.dp, start = 4.dp))
                }
            }
        }
    }
}

@Composable
fun LoadingState(title: String) {
    Column(Modifier.fillMaxSize().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center) {
        CircularProgressIndicator(color = P.accent, strokeWidth = 3.dp)
        Spacer(Modifier.height(14.dp))
        Text("Считаю «$title»…", color = P.muted, fontSize = 14.sp)
        Text("Первый расчёт периода занимает до минуты", color = P.faint, fontSize = 12.sp)
    }
}

@Composable
fun ErrorState(message: String, onRetry: () -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.height(80.dp))
        Icon(Icons.Outlined.CloudOff, null, tint = P.muted, modifier = Modifier.size(40.dp))
        Spacer(Modifier.height(12.dp))
        Text("Не удалось загрузить раздел", color = P.ink, fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(4.dp))
        Text(message, color = P.muted, fontSize = 13.sp)
        Spacer(Modifier.height(16.dp))
        Button(onClick = onRetry) { Text("Повторить") }
    }
}

@Composable
fun SourcesDialog(f: Freshness, onDismiss: () -> Unit) {
    val end = f.end?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("Понятно") } },
        title = { Text("Свежесть данных") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Отчёт строится по ${shortDate(f.end)} включительно: это последний завершённый день 1С.",
                    color = P.muted, fontSize = 13.sp)
                f.sources.forEach { s ->
                    val last = s.last?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
                    val ok = s.ok && last != null && end != null && !last.isBefore(end.minusDays(1))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(8.dp).background(if (ok || s.id == "stock") P.good else P.warn, CircleShape))
                        Spacer(Modifier.width(8.dp))
                        Text(s.name, color = P.ink, fontSize = 14.sp, modifier = Modifier.weight(1f))
                        Text(if (s.ok) shortDate(s.last) else "ошибка", color = P.muted, fontSize = 14.sp)
                    }
                }
                Text("Проверено ${timeStamp(f.checkedAt)}", color = P.faint, fontSize = 11.sp)
            }
        }
    )
}

@Composable
fun SettingsDialog(vm: PulseViewModel, onDismiss: () -> Unit) {
    var url by rememberSaveable { mutableStateOf(vm.repo.endpoint) }
    var token by rememberSaveable { mutableStateOf(vm.repo.token) }
    var status by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Сервер аналитики") },
        text = {
            ConnectionFields(url, { url = it }, token, { token = it }, status, busy)
        },
        confirmButton = {
            TextButton(enabled = url.isNotBlank() && token.isNotBlank() && !busy, onClick = {
                busy = true
                status = "Проверяю…"
                scope.launch {
                    val r = vm.ping(url, token)
                    busy = false
                    r.onSuccess { vm.saveConnection(url, token); onDismiss() }
                        .onFailure { status = it.message ?: "Ошибка" }
                }
            }) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

@Composable
fun ConnectionFields(
    url: String, onUrl: (String) -> Unit, token: String, onToken: (String) -> Unit, status: String?, busy: Boolean
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Адрес и токен хранятся только на этом телефоне.", color = P.muted, fontSize = 13.sp)
        OutlinedTextField(url, onUrl, label = { Text("Адрес, например https://pulse.civi1.ru") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
        OutlinedTextField(token, onToken, label = { Text("Токен доступа") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
        if (status != null) Row(verticalAlignment = Alignment.CenterVertically) {
            if (busy) {
                CircularProgressIndicator(Modifier.size(14.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(8.dp))
            }
            Text(status, color = if (busy) P.muted else P.bad, fontSize = 13.sp)
        }
    }
}

@Composable
fun SetupScreen(vm: PulseViewModel) {
    var url by rememberSaveable { mutableStateOf(vm.repo.endpoint) }
    var token by rememberSaveable { mutableStateOf(vm.repo.token) }
    var status by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().imePadding().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Spacer(Modifier.height(24.dp))
        Text("KIXBOX Pulse", color = P.ink, fontSize = 30.sp, fontWeight = FontWeight.Bold)
        Text("Продажи, розница, клиенты, трафик, реклама, рассылки, доставка, склад и конкуренты — " +
            "из вашего ClickHouse, в одном приложении.", color = P.muted, fontSize = 15.sp, lineHeight = 21.sp)
        Surface(shape = RoundedCornerShape(20.dp), color = P.card) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Подключение", color = P.ink, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                ConnectionFields(url, { url = it }, token, { token = it }, status, busy)
                Button(
                    enabled = url.isNotBlank() && token.isNotBlank() && !busy,
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(14.dp),
                    onClick = {
                        busy = true
                        status = "Проверяю соединение…"
                        scope.launch {
                            val r = vm.ping(url, token)
                            busy = false
                            r.onSuccess { vm.saveConnection(url, token) }.onFailure { status = it.message ?: "Ошибка" }
                        }
                    }
                ) { Text("Подключиться", fontSize = 15.sp) }
            }
        }
        Text("Сервер — сервис backend из репозитория, развёрнутый рядом с ClickHouse. Токен — значение " +
            "SALES_API_TOKEN из его настроек.", color = P.faint, fontSize = 12.sp, lineHeight = 16.sp)
    }
}
