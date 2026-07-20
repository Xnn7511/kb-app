/**
 * 高分子材料原料知识库 v2.0 - 前端应用
 * 左侧分栏 + TDS数据卡片 + 英文标注 + 响应式
 */
const state = {
    currentPage: 'home',
    token: localStorage.getItem('pkb_token') || '',
    isAdmin: localStorage.getItem('pkb_is_admin') === 'true',
    username: localStorage.getItem('pkb_username') || '',
    documents: [],
    docTotal: 0,
    docPage: 1,
    docFilters: { material_type: null, function_tag: null, manufacturer: null, sort_by: 'upload_time', order: 'DESC', search: '' },
    chatHistory: [],
    tags: null,
    sidebarStats: { total: 0, en: 0, tds: 0 },
    selectedDocs: new Set(), // 对比选中的文档ID
    comparisons: [], // 已保存的对比列表
};

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

// ============================================================
// API
// ============================================================
const api = {
    async request(path, options = {}) {
        const url = path.startsWith('http') ? path : `/api${path}`;
        const headers = { ...options.headers };
        if (!headers['Content-Type'] && options.body && !(options.body instanceof FormData))
            headers['Content-Type'] = 'application/json';
        if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
        const res = await fetch(url, { ...options, headers });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }
        return res.json();
    },
    get(path) { return this.request(path); },
    post(path, data) { return this.request(path, { method: 'POST', body: JSON.stringify(data) }); },
    put(path, data) { return this.request(path, { method: 'PUT', body: JSON.stringify(data) }); },
    delete(path) { return this.request(path, { method: 'DELETE' }); },
    async upload(path, formData) {
        const headers = {};
        if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
        const res = await fetch(`/api${path}`, { method: 'POST', body: formData, headers });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }
        return res.json();
    }
};

// ============================================================
// UI 工具
// ============================================================
function toast(msg, type = 'info') {
    const el = $('#toast');
    el.textContent = msg;
    el.className = `toast ${type} show`;
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('show'), 3000);
}
function showModal(html) { $('#modal-content').innerHTML = html; $('#modal-overlay').style.display = 'flex'; }
function closeModal() { $('#modal-overlay').style.display = 'none'; }
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function fmtDate(d) { return d ? new Date(d).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''; }
function fmtSize(b) { if (!b) return '0B'; return b < 1024 ? b + 'B' : b < 1048576 ? (b / 1024).toFixed(1) + 'KB' : (b / 1048576).toFixed(1) + 'MB'; }

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ============================================================
// 导航
// ============================================================
function navigate(page) {
    state.currentPage = page;
    $$('.nav-link[data-page]').forEach(l => l.classList.toggle('active', l.dataset.page === page));
    switch (page) {
        case 'home': renderHome(); break;
        case 'compare': renderCompare(); break;
        case 'experiment': renderExperiment(); break;
        case 'chat': renderChat(); break;
        case 'admin': renderAdmin(); break;
        case 'login': renderLogin(); break;
        default: renderHome();
    }
    window.scrollTo(0, 0);
    $$('.nav-links').forEach(l => l.classList.remove('open'));
}
function updateNavVisibility() {
    $$('.admin-only').forEach(l => l.style.display = state.isAdmin ? '' : 'none');
    $('#loginBtn').style.display = state.isAdmin ? 'none' : '';
    $('#logoutBtn').style.display = state.isAdmin ? '' : 'none';
}

// ============================================================
// 侧边栏
// ============================================================
async function loadSidebar() {
    if (!state.tags) {
        try { state.tags = await api.get('/tags'); } catch (e) { state.tags = { material_types: [], function_tags: [] }; }
    }

    // 从文档统计标签
    let matCounts = {}, funcCounts = {}, mfrCounts = {};
    let enCount = 0, tdsCount = 0;

    try {
        const data = await api.get('/documents?page_size=200');
        state.sidebarStats.total = data.total;
        for (const doc of data.items) {
            for (const t of (doc.material_types || [])) matCounts[t] = (matCounts[t] || 0) + 1;
            for (const f of (doc.function_tags || [])) funcCounts[f] = (funcCounts[f] || 0) + 1;
            const mfr = doc.manufacturer || '未识别';
            if (mfr) mfrCounts[mfr] = (mfrCounts[mfr] || 0) + 1;
            if (doc.language === 'en' || doc.language === 'mixed') enCount++;
            if (doc.tds_data && Object.values(doc.tds_data).some(v => v !== null)) tdsCount++;
        }
    } catch (e) { /* ignore */ }

    state.sidebarStats.en = enCount;
    state.sidebarStats.tds = tdsCount;

    // 渲染材料类型标签
    let matHtml = '';
    const sortedMats = Object.entries(matCounts).sort((a, b) => b[1] - a[1]);
    for (const [name, count] of sortedMats) {
        const active = state.docFilters.material_type === name ? ' active' : '';
        matHtml += `<span class="sidebar-tag material${active}" data-filter="material" data-val="${esc(name)}">${esc(name)}<span class="count">${count}</span></span>`;
    }
    if (state.docFilters.material_type) {
        matHtml += '<span class="sidebar-tag material" data-filter="material" data-val="" style="background:#fee2e2;color:#991b1b">✕ 清除</span>';
    }
    $('#sidebar-material-tags').innerHTML = matHtml || '<span style="font-size:0.75rem;color:var(--gray-400)">加载中...</span>';

    // 渲染功效标签
    let funcHtml = '';
    const sortedFuncs = Object.entries(funcCounts).sort((a, b) => b[1] - a[1]);
    for (const [name, count] of sortedFuncs) {
        const active = state.docFilters.function_tag === name ? ' active' : '';
        funcHtml += `<span class="sidebar-tag function${active}" data-filter="function" data-val="${esc(name)}">${esc(name)}<span class="count">${count}</span></span>`;
    }
    if (state.docFilters.function_tag) {
        funcHtml += '<span class="sidebar-tag function" data-filter="function" data-val="" style="background:#fee2e2;color:#991b1b">✕ 清除</span>';
    }
    $('#sidebar-function-tags').innerHTML = funcHtml || '<span style="font-size:0.75rem;color:var(--gray-400)">加载中...</span>';

    // 渲染厂家标签
    let mfrHtml = '';
    const sortedMfrs = Object.entries(mfrCounts).sort((a, b) => b[1] - a[1]);
    for (const [name, count] of sortedMfrs) {
        const active = state.docFilters.manufacturer === name ? ' active' : '';
        mfrHtml += `<span class="sidebar-tag manufacturer${active}" data-filter="manufacturer" data-val="${esc(name)}">${esc(name)}<span class="count">${count}</span></span>`;
    }
    if (state.docFilters.manufacturer) {
        mfrHtml += '<span class="sidebar-tag manufacturer" data-filter="manufacturer" data-val="" style="background:#fee2e2;color:#991b1b">✕ 清除</span>';
    }
    $('#sidebar-manufacturer-tags').innerHTML = mfrHtml || '<span style="font-size:0.75rem;color:var(--gray-400)">无厂家数据</span>';

    // 统计
    $('#stat-total').textContent = state.sidebarStats.total;
    $('#stat-en').textContent = state.sidebarStats.en;
    $('#stat-tds').textContent = state.sidebarStats.tds;

    // 事件绑定 - 标签点击
    const tagClickHandler = (filterKey) => (e) => {
        const tag = e.target.closest('.sidebar-tag');
        if (!tag) return;
        state.docFilters[filterKey] = tag.dataset.val || null;
        state.docPage = 1;
        renderHome();
    };
    $('#sidebar-material-tags').onclick = tagClickHandler('material_type');
    $('#sidebar-function-tags').onclick = tagClickHandler('function_tag');
    $('#sidebar-manufacturer-tags').onclick = tagClickHandler('manufacturer');

    // 搜索
    $('#sidebar-search').oninput = debounce(() => {
        state.docFilters.search = $('#sidebar-search').value;
        state.docPage = 1;
        loadDocuments();
    }, 400);

    // 侧边栏折叠按钮
    initSidebarToggle();
    // 可折叠区域
    initCollapsibleSections();
}

function initSidebarToggle() {
    const btn = $('#sidebar-toggle');
    const sidebar = $('#sidebar');
    const main = $('#main-content');
    if (!btn) return;
    btn.onclick = () => {
        sidebar.classList.toggle('collapsed');
        btn.classList.toggle('collapsed');
        if (main) main.closest('.main-area').classList.toggle('expanded');
    };
}

function initCollapsibleSections() {
    $$('.sidebar-title.collapsible').forEach(title => {
        title.onclick = () => {
            const targetId = title.dataset.target;
            const target = $('#' + targetId);
            if (target) {
                target.classList.toggle('collapsed');
                title.classList.toggle('collapsed');
            }
        };
    });
}

// ============================================================
// 首页 - 资料库
// ============================================================
async function renderHome() {
    $('#main-content').innerHTML = `
        <div class="page-header">
            <h1>📚 高分子材料原料知识库</h1>
            <p>浏览、检索 ${state.docFilters.material_type ? '「' + esc(state.docFilters.material_type) + '」类' : ''}${state.docFilters.function_tag ? '「' + esc(state.docFilters.function_tag) + '」功效' : ''}${state.docFilters.manufacturer ? '「' + esc(state.docFilters.manufacturer) + '」厂家' : ''} 高分子材料厂商资料</p>
        </div>
        <div class="toolbar">
            <div class="toolbar-group">
                <span class="toolbar-label">排序：</span>
                <select id="home-sort">
                    <option value="upload_time" ${state.docFilters.sort_by === 'upload_time' ? 'selected' : ''}>上传时间</option>
                    <option value="title" ${state.docFilters.sort_by === 'title' ? 'selected' : ''}>标题</option>
                </select>
                <select id="home-order">
                    <option value="DESC" ${state.docFilters.order === 'DESC' ? 'selected' : ''}>最新优先</option>
                    <option value="ASC" ${state.docFilters.order === 'ASC' ? 'selected' : ''}>最早优先</option>
                </select>
            </div>
            <div class="toolbar-group">
                <button class="btn btn-secondary btn-sm" id="clear-select" style="display:none">清除选择</button>
            </div>
        </div>
        <div id="home-content"><div class="loading"><div class="spinner"></div> 加载中...</div></div>
        <div id="home-pagination" style="text-align:center;margin-top:16px"></div>
        <div id="compare-float-btn" class="compare-float-btn" style="display:none">
            <span id="compare-count">0</span> 种材料已选
            <button class="btn btn-primary btn-sm" onclick="startCompare()">开始对比</button>
            <button class="btn btn-secondary btn-sm" onclick="clearSelection()">清除</button>
        </div>`;

    await loadSidebar();
    await loadDocuments();

    $('#home-sort').onchange = (e) => { state.docFilters.sort_by = e.target.value; state.docPage = 1; loadDocuments(); };
    $('#home-order').onchange = (e) => { state.docFilters.order = e.target.value; state.docPage = 1; loadDocuments(); };
    $('#clear-select').onclick = clearSelection;
}

function updateCompareFloatBtn() {
    const btn = $('#compare-float-btn');
    const count = $('#compare-count');
    const clearBtn = $('#clear-select');
    if (state.selectedDocs.size > 0) {
        btn.style.display = 'flex';
        count.textContent = state.selectedDocs.size;
        clearBtn.style.display = '';
    } else {
        btn.style.display = 'none';
        clearBtn.style.display = 'none';
    }
}

function clearSelection() {
    state.selectedDocs.clear();
    updateCompareFloatBtn();
    if (state.currentPage === 'home') loadDocuments();
}

async function startCompare() {
    if (state.selectedDocs.size < 2) {
        toast('至少选择 2 种材料', 'error'); return;
    }
    const docIds = Array.from(state.selectedDocs);
    try {
        const comp = await api.post('/comparisons', { name: `材料对比 ${new Date().toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'})}`, doc_ids: docIds });
        toast('对比创建成功', 'success');
        state.selectedDocs.clear();
        navigate('compare');
    } catch (e) {
        toast(`创建对比失败：${e.message}`, 'error');
    }
}

async function loadDocuments() {
    const content = $('#home-content');
    const pag = $('#home-pagination');
    content.innerHTML = '<div class="loading"><div class="spinner"></div> 加载中...</div>';

    try {
        const params = new URLSearchParams();
        params.set('page', state.docPage);
        params.set('page_size', '20');
        params.set('sort_by', state.docFilters.sort_by);
        params.set('order', state.docFilters.order);
        if (state.docFilters.material_type) params.set('material_type', state.docFilters.material_type);
        if (state.docFilters.function_tag) params.set('function_tag', state.docFilters.function_tag);

        const data = await api.get(`/documents?${params}`);
        state.docTotal = data.total;

        // 前端搜索过滤（包含厂家）
        let docs = data.items;
        if (state.docFilters.manufacturer) {
            docs = docs.filter(d => d.manufacturer === state.docFilters.manufacturer);
        }
        if (state.docFilters.search) {
            const q = state.docFilters.search.toLowerCase();
            docs = docs.filter(d =>
                (d.title && d.title.toLowerCase().includes(q)) ||
                (d.summary && d.summary.toLowerCase().includes(q)) ||
                (d.filename && d.filename.toLowerCase().includes(q))
            );
        }

        if (!docs.length) {
            content.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><h3>暂无匹配资料</h3><p>尝试调整筛选条件</p></div>';
            pag.innerHTML = '';
            return;
        }

        let html = '<div class="doc-grid">';
        for (const doc of docs) {
            const types = doc.material_types || [];
            const funcs = doc.function_tags || [];
            const isEn = doc.language === 'en' || doc.language === 'mixed';
            const isSelected = state.selectedDocs.has(doc.id);

            // TDS 数据
            let tdsHtml = '';
            if (doc.tds_data) {
                const tdsLabels = { mfr: 'MFR', density: '密度', tensile_strength: '拉伸强度', melting_point: '熔点', haze: '雾度', hdt: 'HDT', vicat: '维卡' };
                const tdsUnits = { mfr: 'g/10min', density: 'g/cm³', tensile_strength: 'MPa', melting_point: '°C', haze: '%', hdt: '°C', vicat: '°C' };
                const tdsItems = [];
                for (const [k, v] of Object.entries(doc.tds_data)) {
                    if (v !== null && tdsLabels[k]) {
                        tdsItems.push(`${tdsLabels[k]}: ${v}${tdsUnits[k] || ''}`);
                    }
                }
                if (tdsItems.length) {
                    tdsHtml = '<div class="doc-card-tds">' + tdsItems.slice(0, 4).map(item => `<span class="tds-badge">${esc(item)}</span>`).join('') + '</div>';
                }
            }

            // 标签
            let tagHtml = '<div class="doc-card-tags">';
            for (const t of types.slice(0, 3)) tagHtml += `<span class="tag tag-material">${esc(t)}</span>`;
            for (const f of funcs.slice(0, 3)) tagHtml += `<span class="tag tag-function">${esc(f)}</span>`;
            tagHtml += '</div>';

            html += `
                <div class="doc-card ${isSelected ? 'selected' : ''}" data-doc-id="${doc.id}">
                    <div class="doc-card-select">
                        <input type="checkbox" class="doc-select-box" data-doc-id="${doc.id}" ${isSelected ? 'checked' : ''}>
                    </div>
                    <div class="doc-card-body" onclick="showDocDetail(${doc.id})">
                        <div class="doc-card-header">
                            <div class="doc-card-title">📄 ${esc(doc.title || doc.filename)}</div>
                            ${isEn ? '<span class="doc-card-lang en">EN</span>' : ''}
                        </div>
                        <div class="doc-card-summary">${esc(doc.summary || '暂无摘要')}</div>
                        ${tdsHtml}
                        ${tagHtml}
                        <div class="doc-card-meta">
                            <span>📅 ${fmtDate(doc.upload_time)}</span>
                            <span>📦 ${fmtSize(doc.file_size)}</span>
                        </div>
                    </div>
                </div>`;
        }
        html += '</div>';
        content.innerHTML = html;

        // 点击事件 - 复选框
        content.querySelectorAll('.doc-select-box').forEach(cb => {
            cb.onclick = (e) => {
                e.stopPropagation();
                const id = parseInt(cb.dataset.docId);
                if (cb.checked) {
                    if (state.selectedDocs.size >= 4) {
                        cb.checked = false;
                        toast('最多选择 4 种材料进行对比', 'error');
                        return;
                    }
                    state.selectedDocs.add(id);
                } else {
                    state.selectedDocs.delete(id);
                }
                updateCompareFloatBtn();
                // 更新卡片样式
                const card = cb.closest('.doc-card');
                card.classList.toggle('selected', cb.checked);
            };
        });

        // 标签点击
        content.querySelectorAll('.tag').forEach(t => {
            t.onclick = (e) => {
                e.stopPropagation();
                if (t.classList.contains('tag-material')) {
                    state.docFilters.material_type = state.docFilters.material_type === t.textContent ? null : t.textContent;
                } else {
                    state.docFilters.function_tag = state.docFilters.function_tag === t.textContent ? null : t.textContent;
                }
                state.docPage = 1;
                renderHome();
            };
        });

        // 分页
        const totalPages = Math.ceil(data.total / 20);
        if (totalPages > 1) {
            let pg = '';
            for (let i = 1; i <= totalPages; i++)
                pg += `<button class="btn btn-sm ${i === state.docPage ? 'btn-primary' : 'btn-secondary'}" data-p="${i}">${i}</button>`;
            pag.innerHTML = pg;
            pag.querySelectorAll('button').forEach(b => b.onclick = () => { state.docPage = +b.dataset.p; loadDocuments(); });
        } else { pag.innerHTML = ''; }
    } catch (e) {
        content.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><h3>加载失败</h3><p>${esc(e.message)}</p></div>`;
        pag.innerHTML = '';
    }
}

// ============================================================
// 文档详情弹窗（含TDS表格）
// ============================================================
async function showDocDetail(docId) {
    showModal('<div class="loading"><div class="spinner"></div> 加载中...</div>');
    try {
        const doc = await api.get(`/documents/${docId}`);
        const types = doc.material_types || [];
        const funcs = doc.function_tags || [];
        const isEn = doc.language === 'en' || doc.language === 'mixed';

        // TDS 数据表格
        let tdsTableHtml = '';
        if (doc.tds_data) {
            const tdsLabels = {
                mfr: '熔融指数 (MFR)', density: '密度', tensile_strength: '拉伸强度',
                elongation: '断裂伸长率', flexural_modulus: '弯曲模量', impact_strength: '冲击强度',
                hdt: '热变形温度 (HDT)', vicat: '维卡软化点', melting_point: '熔点',
                haze: '雾度', gloss: '光泽度', ash_content: '灰分'
            };
            const tdsUnits = {
                mfr: 'g/10min', density: 'g/cm³', tensile_strength: 'MPa', elongation: '%',
                flexural_modulus: 'MPa', impact_strength: 'kJ/m²', hdt: '°C', vicat: '°C',
                melting_point: '°C', haze: '%', gloss: '%', ash_content: '%'
            };
            let rows = '';
            let hasData = false;
            for (const [k, label] of Object.entries(tdsLabels)) {
                const v = doc.tds_data[k];
                if (v !== null && v !== undefined) {
                    rows += `<tr><td>${label}</td><td><strong>${v}</strong> ${tdsUnits[k] || ''}</td></tr>`;
                    hasData = true;
                }
            }
            if (hasData) {
                tdsTableHtml = `<h3 style="margin:16px 0 8px">📊 物性数据 (TDS)</h3>
                    <table class="tds-table"><thead><tr><th>检测项目</th><th>数值</th></tr></thead><tbody>${rows}</tbody></table>`;
            }
        }

        let html = `
            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:12px">
                <h2 style="margin:0;font-size:1.2rem">📄 ${esc(doc.title || doc.filename)}</h2>
                <button class="btn btn-secondary btn-sm" onclick="closeModal()">✕ 关闭</button>
            </div>
            <div style="display:flex;gap:12px;color:var(--gray-500);font-size:0.8rem;margin-bottom:12px;flex-wrap:wrap">
                <span>📅 ${fmtDate(doc.upload_time)}</span>
                <span>📦 ${fmtSize(doc.file_size)}</span>
                <span>📝 ${esc(doc.file_type || '')}</span>
                ${isEn ? '<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:10px">🌐 英文资料</span>' : ''}
            </div>
            <div style="margin-bottom:12px">
                <strong>材料类型：</strong>${types.length ? types.map(t => `<span class="tag tag-material">${esc(t)}</span>`).join(' ') : '未分类'}
            </div>
            <div style="margin-bottom:12px">
                <strong>功效特性：</strong>${funcs.length ? funcs.map(t => `<span class="tag tag-function">${esc(t)}</span>`).join(' ') : '未分类'}
            </div>
            ${doc.summary ? `<div style="margin-bottom:12px;padding:10px;background:var(--gray-50);border-radius:var(--radius)"><strong>摘要：</strong>${esc(doc.summary)}</div>` : ''}
            ${tdsTableHtml}
            <h3 style="margin:16px 0 8px">📝 原始文本内容</h3>
            <div class="doc-content">${esc(doc.content_text || '暂无内容')}</div>
            <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
                <a href="/api/documents/${doc.id}/download" class="btn btn-primary btn-sm" target="_blank">⬇ 下载原文</a>
                ${state.isAdmin ? `<button class="btn btn-secondary btn-sm" onclick="editDocument(${doc.id})">✏️ 编辑</button>` : ''}
            </div>`;
        $('#modal-content').innerHTML = html;
    } catch (e) {
        $('#modal-content').innerHTML = `<div class="empty-state"><h3>加载失败</h3><p>${esc(e.message)}</p><button class="btn btn-secondary" onclick="closeModal()">关闭</button></div>`;
    }
}

// ============================================================
// 对比页面
// ============================================================
async function renderCompare() {
    $('#main-content').innerHTML = `
        <div class="page-header"><h1>📊 材料对比</h1><p>并排对比关键性能参数，辅助选材决策</p></div>
        <div id="compare-content"><div class="loading"><div class="spinner"></div> 加载中...</div></div>`;

    try {
        const data = await api.get('/comparisons');
        state.comparisons = data.comparisons || [];
        if (!state.comparisons.length) {
            $('#compare-content').innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📊</div>
                    <h3>暂无对比记录</h3>
                    <p>在资料库页面勾选 2~4 种材料，点击"开始对比"即可创建</p>
                    <button class="btn btn-primary" onclick="navigate('home')">去资料库</button>
                </div>`;
            return;
        }
        renderCompareList();
    } catch (e) {
        $('#compare-content').innerHTML = `<div class="empty-state"><h3>加载失败</h3><p>${esc(e.message)}</p></div>`;
    }
}

function renderCompareList() {
    let html = '<div class="compare-list">';
    for (const comp of state.comparisons) {
        html += `
            <div class="compare-card" data-comp-id="${comp.id}">
                <div class="compare-card-header">
                    <h3>${esc(comp.name)}</h3>
                    <div class="compare-card-actions">
                        <button class="btn btn-primary btn-sm" onclick="viewCompare(${comp.id})">查看对比</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteCompare(${comp.id})">删除</button>
                    </div>
                </div>
                <div class="compare-card-docs">
                    ${comp.doc_ids.map(id => `<span class="tag tag-material">文档 #${id}</span>`).join(' ')}
                </div>
                <div class="compare-card-time">${fmtDate(comp.created_at)}</div>
            </div>`;
    }
    html += '</div>';
    $('#compare-content').innerHTML = html;
}

async function viewCompare(compId) {
    showModal('<div class="loading"><div class="spinner"></div> 加载对比数据...</div>');
    try {
        const comp = await api.get(`/comparisons/${compId}`);
        const docs = comp.documents || [];
        if (docs.length < 2) {
            $('#modal-content').innerHTML = '<div class="empty-state"><h3>对比数据不足</h3><p>需要至少 2 份文档</p></div>';
            return;
        }

        // TDS 标签
        const tdsLabels = {
            mfr: '熔融指数 (MFR)', density: '密度', tensile_strength: '拉伸强度',
            elongation: '断裂伸长率', flexural_modulus: '弯曲模量', impact_strength: '冲击强度',
            hdt: '热变形温度 (HDT)', vicat: '维卡软化点', melting_point: '熔点',
            haze: '雾度', gloss: '光泽度', ash_content: '灰分'
        };
        const tdsUnits = {
            mfr: 'g/10min', density: 'g/cm³', tensile_strength: 'MPa', elongation: '%',
            flexural_modulus: 'MPa', impact_strength: 'kJ/m²', hdt: '°C', vicat: '°C',
            melting_point: '°C', haze: '%', gloss: '%', ash_content: '%'
        };

        // 构建对比表格
        let html = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <h2 style="margin:0;font-size:1.2rem">📊 ${esc(comp.name)}</h2>
            <button class="btn btn-secondary btn-sm" onclick="closeModal()">✕ 关闭</button>
        </div>`;

        // 表格头部
        html += '<div class="compare-table-wrapper"><table class="compare-table"><thead><tr><th style="min-width:120px">对比项</th>';
        for (const doc of docs) {
            html += `<th><div class="compare-doc-header">${esc(doc.title || doc.filename).slice(0, 30)}</div></th>`;
        }
        html += '</tr></thead><tbody>';

        // 基本信息行
        const basicRows = [
            { label: '厂家', key: 'manufacturer', fmt: v => v || '-' },
            { label: '材料类型', key: 'material_types', fmt: v => (v || []).join(', ') || '-' },
            { label: '功效特性', key: 'function_tags', fmt: v => (v || []).join(', ') || '-' },
            { label: '语言', key: 'language', fmt: v => v === 'en' ? '🌐 EN' : v === 'mixed' ? '🌐 混合' : '🇨🇳 中文' },
        ];
        for (const row of basicRows) {
            html += `<tr><td class="compare-row-label">${row.label}</td>`;
            for (const doc of docs) {
                html += `<td>${esc(row.fmt(doc[row.key]))}</td>`;
            }
            html += '</tr>';
        }

        // TDS 数据行
        for (const [key, label] of Object.entries(tdsLabels)) {
            const hasData = docs.some(d => d.tds_data && d.tds_data[key] !== null && d.tds_data[key] !== undefined);
            if (!hasData) continue;
            html += `<tr><td class="compare-row-label">${label} <small style="color:var(--gray-400)">${tdsUnits[key] || ''}</small></td>`;
            for (const doc of docs) {
                const v = doc.tds_data ? doc.tds_data[key] : null;
                html += `<td class="compare-value ${v !== null ? 'has-value' : 'no-value'}">${v !== null ? `<strong>${v}</strong>` : '<span style="color:var(--gray-400)">-</span>'}</td>`;
            }
            html += '</tr>';
        }

        // 摘要行
        html += `<tr><td class="compare-row-label">摘要</td>`;
        for (const doc of docs) {
            html += `<td style="font-size:0.8rem;max-width:200px">${esc((doc.summary || '-').slice(0, 100))}</td>`;
        }
        html += '</tr>';

        // 操作行
        html += `<tr><td class="compare-row-label">操作</td>`;
        for (const doc of docs) {
            html += `<td><button class="btn btn-primary btn-sm" onclick="closeModal();setTimeout(()=>showDocDetail(${doc.id}),50)">查看详情</button></td>`;
        }
        html += '</tr>';

        html += '</tbody></table></div>';
        $('#modal-content').innerHTML = html;
    } catch (e) {
        $('#modal-content').innerHTML = `<div class="empty-state"><h3>加载失败</h3><p>${esc(e.message)}</p><button class="btn btn-secondary" onclick="closeModal()">关闭</button></div>`;
    }
}

async function deleteCompare(compId) {
    if (!confirm('确定删除此对比？')) return;
    try {
        await api.delete(`/comparisons/${compId}`);
        toast('删除成功', 'success');
        state.comparisons = state.comparisons.filter(c => c.id !== compId);
        renderCompareList();
    } catch (e) { toast(`删除失败：${e.message}`, 'error'); }
}

// ============================================================
// 智能问答
// ============================================================
function renderChat() {
    $('#main-content').innerHTML = `
        <div class="page-header"><h1>💬 智能问答</h1><p>基于知识库内容回答高分子材料相关问题</p></div>
        <div class="chat-container">
            <div class="chat-messages" id="chat-messages">
                <div class="chat-message assistant">👋 您好！我是高分子材料知识助手。您可以问我关于材料特性、配方、工艺等方面的问题。</div>
            </div>
            <div class="chat-input-area">
                <input type="text" id="chat-input" placeholder="输入问题，如：BOPP抗粘母料有哪些推荐？" />
                <button class="btn btn-primary" id="chat-send">发送</button>
                <button class="btn btn-secondary btn-sm" id="chat-clear">清空</button>
            </div>
        </div>`;

    const mc = $('#chat-messages');
    for (const msg of state.chatHistory) appendChatMsg(msg.role, msg.content, msg.refs);
    mc.scrollTop = mc.scrollHeight;
    $('#chat-send').onclick = sendChat;
    $('#chat-input').onkeydown = e => { if (e.key === 'Enter') sendChat(); };
    $('#chat-clear').onclick = () => { state.chatHistory = []; renderChat(); };
}

function appendChatMsg(role, content, refs) {
    const mc = $('#chat-messages');
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;
    let html = content.replace(/\n/g, '<br>');
    if (refs && refs.length) {
        html += '<div style="margin-top:8px;font-size:0.78rem"><strong>📚 参考：</strong>';
        for (const r of refs) html += `<span class="tag tag-material" style="cursor:pointer" data-doc-id="${r.document_id}">📄 ${esc(r.title || r.filename)}</span> `;
        html += '</div>';
    }
    div.innerHTML = html;
    mc.appendChild(div);
    div.querySelectorAll('.tag[data-doc-id]').forEach(t => t.onclick = () => showDocDetail(t.dataset.docId));
    mc.scrollTop = mc.scrollHeight;
}

async function sendChat() {
    const input = $('#chat-input');
    const q = input.value.trim();
    if (!q) return;
    input.value = '';
    appendChatMsg('user', q);
    state.chatHistory.push({ role: 'user', content: q });

    const mc = $('#chat-messages');
    const ld = document.createElement('div');
    ld.className = 'chat-message assistant';
    ld.innerHTML = '<div class="spinner"></div> 检索中...';
    mc.appendChild(ld);
    mc.scrollTop = mc.scrollHeight;

    try {
        const data = await api.post('/chat', { query: q, history: state.chatHistory.slice(0, -1), top_k: 5 });
        ld.remove();
        appendChatMsg('assistant', data.answer, data.references);
        state.chatHistory.push({ role: 'assistant', content: data.answer, refs: data.references });
    } catch (e) {
        ld.remove();
        appendChatMsg('assistant', `请求失败：${e.message}`);
        state.chatHistory.push({ role: 'assistant', content: `请求失败：${e.message}` });
    }
}

// ============================================================
// 实验方案
// ============================================================
let expState = { goal: '', plan: '', review: '', history: [] };

function renderExperiment() {
    expState = { goal: '', plan: '', review: '', history: [] };
    $('#main-content').innerHTML = `
        <div class="page-header"><h1>🔬 实验方案智能分析</h1><p>输入实验目标，系统融合知识库+专业知识，自动生成方案并经专家反审</p></div>
        <div class="experiment-container">
            <div class="experiment-form" id="exp-form-area">
                <div class="form-group"><label>🎯 实验目标（必填）</label>
                    <textarea id="exp-goal" placeholder="例如：开发一种高韧性阻燃PP材料，需V0级并保持冲击强度"></textarea></div>
                <div class="form-group"><label>📋 约束条件（可选）</label>
                    <textarea id="exp-constraints" placeholder="例如：成本控制在20元/kg以内，加工温度不超过230°C"></textarea></div>
                <button class="btn btn-primary btn-lg" id="exp-submit">🚀 生成实验方案</button>
            </div>
            <div id="exp-result"></div>
            <div id="exp-followup" style="display:none">
                <div class="chat-container" style="margin-top:16px">
                    <h3 style="margin-bottom:8px">💬 方案追问</h3>
                    <div class="chat-messages" id="exp-chat-messages" style="max-height:400px;overflow-y:auto"></div>
                    <div class="chat-input-area">
                        <input type="text" id="exp-followup-input" placeholder="针对方案提问，如：推荐多少添加量？有什么替代方案？" />
                        <button class="btn btn-primary" id="exp-followup-send">发送</button>
                        <button class="btn btn-secondary btn-sm" id="exp-followup-reset">重新生成</button>
                    </div>
                </div>
            </div>
        </div>`;

    $('#exp-submit').onclick = async () => {
        const goal = $('#exp-goal').value.trim();
        if (!goal) { toast('请输入实验目标', 'error'); return; }
        const btn = $('#exp-submit');
        btn.disabled = true; btn.textContent = '⏳ 生成中（含专家反审）...';
        $('#exp-result').innerHTML = '<div class="card" style="text-align:center;padding:30px"><div class="spinner" style="width:30px;height:30px;margin:0 auto 12px"></div><p>融合知识库资料，生成方案并进行专家反审...</p></div>';
        try {
            const data = await api.post('/experiment', { goal, constraints: $('#exp-constraints').value.trim() });
            expState.goal = goal;
            expState.plan = data.plan;
            expState.review = data.review_notes;
            expState.history = [{ role: 'assistant', content: `实验方案已生成：${goal}` }];
            $('#exp-result').innerHTML = `
                <div class="result-section"><h2>📋 最终实验方案（经专家反审修正）</h2><div class="markdown-body">${data.plan.replace(/\n/g,'<br>')}</div></div>
                <div class="result-section review-box"><h2>🔍 专家反审备注</h2><div class="markdown-body">${data.review_notes.replace(/\n/g,'<br>')}</div></div>`;
            $('#exp-followup').style.display = 'block';
            $('#exp-followup-input').focus();
            setupFollowup();
        } catch (e) {
            $('#exp-result').innerHTML = `<div class="card" style="text-align:center;padding:30px;color:var(--danger)">❌ ${esc(e.message)}</div>`;
        } finally { btn.disabled = false; btn.textContent = '🚀 生成实验方案'; }
    };
}

function setupFollowup() {
    const mc = $('#exp-chat-messages');
    mc.innerHTML = '';
    appendExpChat('assistant', '方案已生成，您可以针对方案内容继续追问。例如：推荐多少添加量？有什么替代方案？修改加工温度建议？');

    $('#exp-followup-send').onclick = sendExpFollowup;
    $('#exp-followup-input').onkeydown = e => { if (e.key === 'Enter') sendExpFollowup(); };
    $('#exp-followup-reset').onclick = () => { expState = {}; renderExperiment(); };
}

function appendExpChat(role, content) {
    const mc = $('#exp-chat-messages');
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;
    div.innerHTML = content.replace(/\n/g, '<br>');
    mc.appendChild(div);
    mc.scrollTop = mc.scrollHeight;
}

async function sendExpFollowup() {
    const input = $('#exp-followup-input');
    const q = input.value.trim();
    if (!q) return;
    input.value = '';
    appendExpChat('user', q);
    expState.history.push({ role: 'user', content: q });

    const mc = $('#exp-chat-messages');
    const ld = document.createElement('div');
    ld.className = 'chat-message assistant';
    ld.innerHTML = '<div class="spinner"></div> 分析中...';
    mc.appendChild(ld);
    mc.scrollTop = mc.scrollHeight;

    try {
        // 将方案上下文 + 追问一起发送
        const contextMsg = `基于以下实验方案回答追问：\n\n方案目标：${expState.goal}\n\n方案内容：${expState.plan.slice(0, 2000)}\n\n追问：${q}`;
        const data = await api.post('/chat', { query: contextMsg, history: expState.history.slice(0, -1), top_k: 3 });
        ld.remove();
        appendExpChat('assistant', data.answer);
        expState.history.push({ role: 'assistant', content: data.answer });
    } catch (e) {
        ld.remove();
        appendExpChat('assistant', `请求失败：${e.message}`);
    }
}

// ============================================================
// 管理后台
// ============================================================
async function renderAdmin() {
    if (!state.isAdmin) { navigate('login'); return; }
    $('#main-content').innerHTML = `
        <div class="page-header"><h1>⚙️ 管理后台</h1><p>上传、编辑和管理知识库资料</p></div>
        <div class="admin-container">
            <div class="upload-zone" id="upload-zone">
                <div class="upload-icon">📤</div>
                <div>点击或拖拽文件上传（PDF/Word/TXT/CSV/Excel）</div>
                <input type="file" id="file-input" multiple accept=".pdf,.docx,.doc,.txt,.md,.csv,.xlsx,.xls" style="display:none">
                <div id="upload-progress" style="margin-top:8px"></div>
            </div>
            <h3 style="margin-bottom:12px">📋 已上传资料 (${state.sidebarStats.total} 份)</h3>
            <div id="admin-docs-table"></div>
        </div>`;

    const zone = $('#upload-zone'), fi = $('#file-input');
    zone.onclick = () => fi.click();
    zone.ondragover = e => { e.preventDefault(); zone.classList.add('drag-over'); };
    zone.ondragleave = () => zone.classList.remove('drag-over');
    zone.ondrop = e => { e.preventDefault(); zone.classList.remove('drag-over'); handleUpload(e.dataTransfer.files); };
    fi.onchange = () => handleUpload(fi.files);
    await loadAdminDocs();
}

async function handleUpload(files) {
    if (!files.length) return;
    const prog = $('#upload-progress');
    for (const file of files) {
        prog.innerHTML = `<div class="spinner"></div> 上传中：${esc(file.name)}...`;
        const fd = new FormData(); fd.append('file', file);
        try {
            const r = await api.upload('/documents/upload', fd);
            if (r.duplicate) prog.innerHTML = `⚠️ ${esc(file.name)} 已存在，跳过`;
            else {
                prog.innerHTML = `✅ ${esc(file.name)} 上传成功！`;
                if (r.material_types && r.material_types.length) prog.innerHTML += `<br><small>材料：${r.material_types.join(', ')}</small>`;
                if (r.function_tags && r.function_tags.length) prog.innerHTML += `<br><small>功效：${r.function_tags.join(', ')}</small>`;
            }
        } catch (e) { prog.innerHTML = `❌ ${esc(file.name)} 失败：${esc(e.message)}`; }
        await new Promise(r => setTimeout(r, 600));
    }
    await loadAdminDocs();
    await loadSidebar();
}

async function loadAdminDocs() {
    const div = $('#admin-docs-table');
    div.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
        const data = await api.get('/documents?page_size=100');
        if (!data.items.length) { div.innerHTML = '<div class="empty-state"><p>暂无资料</p></div>'; return; }
        let html = '<table class="admin-table"><thead><tr><th>ID</th><th>标题</th><th>材料</th><th>功效</th><th>语言</th><th>大小</th><th>时间</th><th>操作</th></tr></thead><tbody>';
        for (const d of data.items) {
            html += `<tr>
                <td>${d.id}</td><td><strong>${esc((d.title||d.filename).slice(0,40))}</strong></td>
                <td>${(d.material_types||[]).slice(0,2).map(t=>`<span class="tag tag-material">${esc(t)}</span>`).join('')}</td>
                <td>${(d.function_tags||[]).slice(0,2).map(t=>`<span class="tag tag-function">${esc(t)}</span>`).join('')}</td>
                <td>${d.language==='en'?'🌐 EN':d.language==='mixed'?'🌐 混合':'🇨🇳'}</td>
                <td>${fmtSize(d.file_size)}</td><td>${fmtDate(d.upload_time)}</td>
                <td><button class="btn btn-secondary btn-sm" onclick="editDocument(${d.id})">✏️</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteDocument(${d.id})">🗑</button></td></tr>`;
        }
        html += '</tbody></table>';
        div.innerHTML = html;
    } catch (e) { div.innerHTML = `<div class="empty-state"><p>加载失败：${esc(e.message)}</p></div>`; }
}

async function editDocument(docId) {
    try {
        const doc = await api.get(`/documents/${docId}`);
        if (!state.tags) state.tags = await api.get('/tags');
        let selMat = [...(doc.material_types||[])];
        let selFunc = [...(doc.function_tags||[])];

        let html = `<h2>✏️ 编辑 #${doc.id}</h2>
            <div class="form-group"><label>标题</label><input type="text" id="et" value="${esc(doc.title||'')}" class="form-group input" style="width:100%"></div>
            <div class="form-group"><label>摘要</label><textarea id="es" style="width:100%;min-height:60px">${esc(doc.summary||'')}</textarea></div>
            <div class="form-group"><label>材料类型</label><div class="sidebar-tags" id="emt">${state.tags.material_types.map(t=>`<span class="sidebar-tag material ${selMat.includes(t)?'active':''}" data-v="${esc(t)}">${esc(t)}</span>`).join('')}</div></div>
            <div class="form-group"><label>功效特性</label><div class="sidebar-tags" id="eft">${state.tags.function_tags.map(t=>`<span class="sidebar-tag function ${selFunc.includes(t)?'active':''}" data-v="${esc(t)}">${esc(t)}</span>`).join('')}</div></div>
            <div style="display:flex;gap:8px;margin-top:16px"><button class="btn btn-primary" id="se">💾 保存</button><button class="btn btn-secondary" onclick="closeModal()">取消</button></div>`;
        showModal(html);

        $('#emt').onclick = (e) => {
            const t = e.target.closest('.sidebar-tag'); if (!t) return;
            t.classList.toggle('active');
            const v = t.dataset.v;
            selMat = t.classList.contains('active') ? [...new Set([...selMat, v])] : selMat.filter(x => x !== v);
        };
        $('#eft').onclick = (e) => {
            const t = e.target.closest('.sidebar-tag'); if (!t) return;
            t.classList.toggle('active');
            const v = t.dataset.v;
            selFunc = t.classList.contains('active') ? [...new Set([...selFunc, v])] : selFunc.filter(x => x !== v);
        };
        $('#se').onclick = async () => {
            try {
                await api.put(`/documents/${docId}`, { title: $('#et').value.trim() || doc.title, summary: $('#es').value.trim() || doc.summary, material_types: selMat, function_tags: selFunc });
                toast('保存成功', 'success'); closeModal();
                if (state.currentPage === 'admin') await loadAdminDocs();
                await loadSidebar();
            } catch (e) { toast(`保存失败：${e.message}`, 'error'); }
        };
    } catch (e) { toast(`加载失败：${e.message}`, 'error'); closeModal(); }
}

async function deleteDocument(docId) {
    if (!confirm('确定删除？')) return;
    try { await api.delete(`/documents/${docId}`); toast('删除成功', 'success'); await loadAdminDocs(); await loadSidebar(); }
    catch (e) { toast(`删除失败：${e.message}`, 'error'); }
}

// ============================================================
// 登录
// ============================================================
async function renderLogin() {
    let hasAdmin = false;
    try { hasAdmin = (await api.get('/auth/status')).has_admin; } catch (e) { }
    const isInit = !hasAdmin;
    $('#main-content').innerHTML = `
        <div class="login-container"><div class="card" style="padding:24px">
            <h1>${isInit ? '🔐 初始化管理员' : '🔑 管理员登录'}</h1>
            <p style="text-align:center;color:var(--gray-500);margin-bottom:16px;font-size:0.85rem">${isInit ? '首次使用，请创建管理员账号' : '请输入管理员账号密码'}</p>
            <div class="form-group"><label>用户名</label><input type="text" id="lu" placeholder="用户名" autocomplete="username"></div>
            <div class="form-group"><label>密码</label><input type="password" id="lp" placeholder="密码" autocomplete="${isInit?'new-password':'current-password'}"></div>
            <button class="btn btn-primary btn-lg" style="width:100%" id="ls">${isInit ? '创建管理员' : '登录'}</button>
            <div id="le" style="color:var(--danger);font-size:0.8rem;margin-top:10px;text-align:center"></div>
        </div></div>`;

    $('#ls').onclick = async () => {
        const u = $('#lu').value.trim(), p = $('#lp').value.trim();
        if (!u || !p) { $('#le').textContent = '请填写用户名和密码'; return; }
        try {
            const r = isInit ? await api.post('/auth/init-admin', { username: u, password: p })
                : await api.post('/auth/login', { username: u, password: p });
            state.token = r.access_token; state.isAdmin = r.is_admin; state.username = u;
            localStorage.setItem('pkb_token', r.access_token); localStorage.setItem('pkb_is_admin', r.is_admin); localStorage.setItem('pkb_username', u);
            updateNavVisibility();
            toast(isInit ? '管理员创建成功！' : '登录成功！', 'success');
            navigate('admin');
        } catch (e) { $('#le').textContent = e.message; }
    };
    $('#lp').onkeydown = e => { if (e.key === 'Enter') $('#ls').click(); };
}

// ============================================================
// 初始化
// ============================================================
function init() {
    updateNavVisibility();
    $$('.nav-link[data-page]').forEach(l => l.onclick = (e) => {
        e.preventDefault();
        const p = l.dataset.page;
        if (p === 'logout') {
            state.token = ''; state.isAdmin = false; state.username = '';
            ['pkb_token', 'pkb_is_admin', 'pkb_username'].forEach(k => localStorage.removeItem(k));
            updateNavVisibility(); toast('已退出', 'info'); navigate('home'); return;
        }
        navigate(p);
    });
    $('#logoutBtn').onclick = (e) => {
        e.preventDefault();
        state.token = ''; state.isAdmin = false; state.username = '';
        ['pkb_token', 'pkb_is_admin', 'pkb_username'].forEach(k => localStorage.removeItem(k));
        updateNavVisibility(); toast('已退出', 'info'); navigate('home');
    };
    $('#modal-overlay').onclick = (e) => { if (e.target === $('#modal-overlay')) closeModal(); };
    $('#navToggle').onclick = () => $$('.nav-links').forEach(l => l.classList.toggle('open'));
    document.onkeydown = (e) => { if (e.key === 'Escape') closeModal(); };
    navigate('home');
}

document.addEventListener('DOMContentLoaded', init);
