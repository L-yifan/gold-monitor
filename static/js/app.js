const { createApp } = Vue;

createApp({
    data() {
        return {
            isDarkMode: true,
            currentView: 'gold',
            funds: [],
            newFundCode: '',
            fundFilterText: '',
            fundSortMode: 'default',
            isAddingFund: false,
            holdings: [],
            holdingsSummary: { total_cost: 0, total_value: 0, total_profit: 0, total_profit_rate: 0, count: 0 },
            holdingsLastUpdate: '--',
            isLoadingHoldings: false,
            holdingsTimer: null,
            fundPriceAnimating: false,
            priceAnimating: false,
            holdingModal: {
                visible: false,
                isEdit: false,
                code: '',
                costPrice: '',
                shares: '',
                note: '',
                saving: false
            },
            portfolioDrawer: {
                visible: false,
                loading: false,
                fundName: '',
                fundCode: '',
                holdings: [],
                meta: { weight_coverage: 0, contribution_available: false, confidence_label: '--', report_period: '', estimate_mode: 'none' }
            },
            isInitialLoading: true,
            fetchError: null,
            currentData: { price: 0, change: 0, open: 0, yesterday_close: 0, high: 0, low: 0, time_str: '--:--:--' },
            buyPrice: 0,
            buyWeight: 1,
            records: [],
            historyData: [],
            chartViewMode: '30M',
            isConnected: false,
            isRecording: false,
            hasInitializedBuyPrice: false,
            priceTimer: null,
            fundTimer: null,
            lastPriceInterval: null,
            lastFundInterval: null,
            tempBuyPrice: null,
            chartSwitching: false,
            timeAnimating: false,
            fundTimeAnimating: false,
            priceAnimTimer: null,
            timeAnimTimer: null,
            fundTimeAnimTimer: null,
            isFirstLoad: true,
            cardsAnimated: false,
            settings: { high: 0, low: 0, enabled: false, trading_events_enabled: true },
            lastNotifiedTime: 0,
            tradingStatus: { is_trading_time: false, trading_phase: 'closed', phase_name: '休市', next_event: null, next_event_time: null, time_until_next: null, is_holiday: false, holiday_name: null, weekday: 0, weekday_name: '' },
            fundTradingStatus: { is_trading_time: false, trading_phase: 'closed', phase_name: '休市', next_event: null, next_event_time: null, time_until_next: null, is_holiday: false, holiday_name: null, weekday: 0, weekday_name: '' },
            lastTradingPhase: null,
            lastFundTradingPhase: null,
            tradingTimer: null,
            isRibbonHovered: false,
            modal: { visible: false, type: 'prompt', title: '', message: '', placeholder: '', inputValue: '', confirmText: '确定', confirmButtonClass: '', resolve: null },
            holdingsPulse: { todayProfit: false, totalProfit: false, profitRate: false, timers: { todayProfit: null, totalProfit: null, profitRate: null } },
            isHoldingsListCollapsed: false,
            holdingsListHeight: 2000,
            holdingsListTransitionEnabled: true,
            isHoldingsListExpanding: false,
            fundDisplayMode: 'card',
            fundSortField: 'default',
            fundSortDirection: 'desc',
            fundRowHeight: 'comfortable',
            chartInitialized: false,
            chartAnimationPhase: 'none'
        };
    },
    created() {
        this.chartInstance = null;
        this.loadFundViewPreferences();
    },
    watch: {
        'portfolioDrawer.visible'(newVal) {
            document.body.style.overflow = newVal ? 'hidden' : '';
        },
        async currentView(newVal) {
            if (newVal === 'fund') {
                if (this.priceTimer) { clearInterval(this.priceTimer); this.priceTimer = null; }
                if (this.chartInstance) { this.chartInstance.destroy(); this.chartInstance = null; }
                await this.fetchTradingStatus('fund');
                this.fetchFunds(true);
                this.fetchHoldings(true);
                this.startFundPolling();
            } else {
                if (this.fundTimer) { clearInterval(this.fundTimer); this.fundTimer = null; }
                await this.fetchTradingStatus('gold');
                this.chartInitialized = false;
                this.chartAnimationPhase = 'none';
                this.fetchHistory();
                this.fetchPrice();
                this.startPricePolling();
            }
        },
        holdingsSummary: {
            handler(newVal, oldVal) {
                if (!oldVal || (newVal.count === 0 && oldVal.count === 0) || newVal.count === oldVal.count) return;
                if (newVal.total_today_profit !== oldVal.total_today_profit) this.triggerPulse('todayProfit');
                if (newVal.total_profit !== oldVal.total_profit) this.triggerPulse('totalProfit');
                if (newVal.total_profit_rate !== oldVal.total_profit_rate) this.triggerPulse('profitRate');
            },
            deep: true
        },
        isHoldingsListCollapsed(newVal) {
            if (!newVal) {
                this.isHoldingsListExpanding = true;
                this.holdingsListHeight = 2000;
                setTimeout(() => {
                    this.isHoldingsListExpanding = false;
                    this.updateHoldingsListHeight();
                }, 500);
            }
        },
        holdings: {
            handler() { this.$nextTick(() => { this.updateHoldingsListHeight(); }); },
            deep: true
        },
        fundRowHeight() { this.saveFundViewPreferences(); },
        isInitialLoading(newVal) {
            if (!newVal && this.isFirstLoad) {
                this.$nextTick(() => {
                    setTimeout(() => { this.cardsAnimated = true; this.isFirstLoad = false; }, 1200);
                });
            }
        }
    },
    computed: {
        totalTodayProfit() { return this.holdings.reduce((sum, h) => sum + (h.today_profit || 0), 0); },
        portfolioContribution() {
            const holdings = this.portfolioDrawer.holdings || [];
            const meta = this.portfolioDrawer.meta || {};
            if (!holdings.length || meta.contribution_available === false) return { available: false, value: 0 };
            const total = holdings.reduce((sum, stock) => sum + (typeof stock.contribution === 'number' ? stock.contribution : 0), 0);
            return { available: true, value: total };
        },
        filteredFunds() {
            let result = [...this.funds];
            if (this.fundFilterText) {
                const q = this.fundFilterText.toLowerCase();
                result = result.filter(f => f.name.toLowerCase().includes(q) || f.code.toLowerCase().includes(q));
            }
            const sortDir = this.fundSortDirection === 'asc' ? 1 : -1;
            if (this.fundSortField !== 'default') {
                switch (this.fundSortField) {
                    case 'change': result.sort((a, b) => sortDir * (a.change - b.change)); break;
                    case 'price': result.sort((a, b) => sortDir * (parseFloat(a.price) - parseFloat(b.price))); break;
                    case 'name': result.sort((a, b) => sortDir * a.name.localeCompare(b.name, 'zh-CN')); break;
                }
            } else {
                if (this.fundSortMode === 'gain') result.sort((a, b) => b.change - a.change);
                else if (this.fundSortMode === 'loss') result.sort((a, b) => a.change - b.change);
            }
            return result;
        },
        isPriceUp() { return this.currentData.change >= 0; },
        currentProfit() {
            if (!this.buyPrice || this.buyPrice <= 0 || !this.currentData.price) return { rate: '0.00', amount: '0.00' };
            const feeRate = 0.005;
            const actualReceive = this.currentData.price * (1 - feeRate);
            const rate = ((actualReceive - this.buyPrice) / this.buyPrice * 100);
            let amount = actualReceive - this.buyPrice;
            if (this.buyWeight && this.buyWeight > 0) amount = amount * this.buyWeight;
            return { rate: rate.toFixed(2), amount: amount.toFixed(2) };
        },
        profitBarStyle() {
            const rate = parseFloat(this.currentProfit.rate);
            const clampedRate = Math.min(20, Math.max(-10, rate));
            const zeroPos = 33.3333; // 0% point position

            if (clampedRate < 0) {
                // Loss: fill to the left from zeroPos
                const width = (Math.abs(clampedRate) / 10) * zeroPos;
                return { width: `${width}%`, left: `${zeroPos - width}%` };
            } else {
                // Profit: fill to the right from zeroPos
                const width = (clampedRate / 20) * (100 - zeroPos);
                return { width: `${width}%`, left: `${zeroPos}%` };
            }
        },
        profitMarkerStyle() {
            const rate = parseFloat(this.currentProfit.rate);
            const clampedRate = Math.min(20, Math.max(-10, rate));
            const zeroPos = 33.3333;
            let left = zeroPos;

            if (clampedRate < 0) {
                left = zeroPos - (Math.abs(clampedRate) / 10) * zeroPos;
            } else {
                left = zeroPos + (clampedRate / 20) * (100 - zeroPos);
            }
            return { left: `${left}%` };
        },
        targetTable() {
            if (!this.buyPrice || this.buyPrice <= 0) return [];
            const targets = [5, 10, 15, 20, 30];
            const feeRate = 0.005;
            return targets.map(percent => {
                const sellPrice = this.buyPrice * (1 + percent / 100) / (1 - feeRate);
                let profitAmount = (this.buyPrice * percent / 100);
                if (this.buyWeight && this.buyWeight > 0) profitAmount = profitAmount * this.buyWeight;
                const requiredGain = ((sellPrice - this.buyPrice) / this.buyPrice * 100);
                const reached = this.currentData.price >= sellPrice;
                const progress = Math.min(100, Math.max(0, (this.currentData.price - this.buyPrice) / (sellPrice - this.buyPrice) * 100));
                return { percent, sellPrice: sellPrice.toFixed(2), profitAmount: profitAmount.toFixed(2), requiredGain: requiredGain.toFixed(2), reached, progress: progress.toFixed(1) };
            });
        },
        reversedRecords() { return [...this.records].reverse(); },
        chartContainerClass() {
            if (!this.chartInitialized) return 'opacity-0';
            if (this.chartAnimationPhase === 'initial') return 'chart-reveal-clip';
            if (this.chartAnimationPhase === 'switch') return 'chart-view-switching';
            return 'chart-visible';
        }
    },
    methods: {
        formatPrice(price) { return (price === undefined || price === null || isNaN(price)) ? '--' : parseFloat(price).toFixed(2); },
        formatAmount(amount) { return (amount === undefined || amount === null || isNaN(amount)) ? '--' : parseFloat(amount).toFixed(2); },
        formatPercent(val) { return (val === undefined || val === null || isNaN(val)) ? '0.00' : (val >= 0 ? '+' : '') + parseFloat(val).toFixed(2); },
        toggleTheme() {
            // 性能优化：在切换主题前临时禁用所有过渡效果，防止大量元素同时重绘导致的卡顿
            document.documentElement.classList.add('no-transitions');

            const theme = this.isDarkMode ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            if (this.chartInstance) {
                this.resetChartLoader();
            }

            // 在下一帧移除禁用类，恢复正常的交互过渡（如 hover 效果）
            requestAnimationFrame(() => {
                // 需要双重帧确保属性变更已被浏览器捕获并跳过过渡
                requestAnimationFrame(() => {
                    document.documentElement.classList.remove('no-transitions');
                });
            });
        },
        loadTheme() {
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme) {
                this.isDarkMode = savedTheme === 'dark';
            } else {
                this.isDarkMode = !window.matchMedia('(prefers-color-scheme: light)').matches;
            }
            // 已经在 index.html 的内联脚本中处理了属性设置，这里同步 Vue 状态即可
            document.documentElement.setAttribute('data-theme', this.isDarkMode ? 'dark' : 'light');
        },
        resetChartLoader() {
            this.chartInitialized = false;
            if (this.chartInstance) {
                this.chartInstance.destroy();
                this.chartInstance = null;
            }
            if (this.historyData.length > 0) {
                this.$nextTick(() => this.initChart());
            }
        },
        loadFundViewPreferences() {
            try {
                const saved = localStorage.getItem('fundViewPreferences');
                if (saved) {
                    const prefs = JSON.parse(saved);
                    if (prefs.displayMode) this.fundDisplayMode = prefs.displayMode;
                    if (prefs.sortField) this.fundSortField = prefs.sortField;
                    if (prefs.sortDirection) this.fundSortDirection = prefs.sortDirection;
                    if (prefs.rowHeight) this.fundRowHeight = prefs.rowHeight;
                }
            } catch (e) { console.warn('加载基金视图偏好失败:', e); }
        },
        saveFundViewPreferences() {
            try {
                localStorage.setItem('fundViewPreferences', JSON.stringify({
                    displayMode: this.fundDisplayMode,
                    sortField: this.fundSortField,
                    sortDirection: this.fundSortDirection,
                    rowHeight: this.fundRowHeight
                }));
            } catch (e) { console.warn('保存基金视图偏好失败:', e); }
        },
        setFundDisplayMode(mode) { this.fundDisplayMode = mode; this.saveFundViewPreferences(); },
        setLegacyFundSortMode(mode) {
            this.fundSortMode = mode;
            this.fundSortField = 'default';
            this.fundSortDirection = mode === 'loss' ? 'asc' : 'desc';
            this.saveFundViewPreferences();
        },
        toggleSort(field) {
            if (this.fundSortField === field) { this.fundSortDirection = this.fundSortDirection === 'asc' ? 'desc' : 'asc'; }
            else { this.fundSortField = field; this.fundSortDirection = 'desc'; }
            this.fundSortMode = 'default';
            this.saveFundViewPreferences();
        },
        getSortClass(field) {
            if (this.fundSortField !== field) return '';
            return this.fundSortDirection === 'asc' ? 'sort-asc' : 'sort-desc';
        },
        updateHoldingsListHeight() {
            if (this.isHoldingsListExpanding) return;
            if (this.$refs.holdingsListRef) {
                this.holdingsListTransitionEnabled = false;
                this.holdingsListHeight = Math.max(this.$refs.holdingsListRef.scrollHeight, 100);
                requestAnimationFrame(() => { this.holdingsListTransitionEnabled = true; });
            }
        },
        triggerPulse(field) {
            const timer = this.holdingsPulse.timers[field];
            if (timer) { clearTimeout(timer); this.holdingsPulse.timers[field] = null; }
            this.holdingsPulse[field] = false;
            this.$nextTick(() => { this.holdingsPulse[field] = true; });
            this.holdingsPulse.timers[field] = setTimeout(() => { this.holdingsPulse[field] = false; this.holdingsPulse.timers[field] = null; }, 1000);
        },
        async fetchTradingStatus(type = 'gold') {
            try {
                const res = await fetch(`/api/trading-status?type=${type}`);
                const data = await res.json();
                if (data.success) {
                    if (type === 'gold') {
                        this.tradingStatus = data.data;
                        if (!this.lastTradingPhase) this.lastTradingPhase = data.data.trading_phase;
                    } else {
                        this.fundTradingStatus = data.data;
                        if (!this.lastFundTradingPhase) this.lastFundTradingPhase = data.data.trading_phase;
                    }
                }
            } catch (e) { console.error(`获取${type}交易状态失败`, e); }
        },
        async checkTradingEvents() {
            try { await Promise.all([this._checkSingleEvent('gold'), this._checkSingleEvent('fund')]); } catch (e) { console.error('检查交易事件失败', e); }
        },
        async _checkSingleEvent(type) {
            const res = await fetch(`/api/trading-status?type=${type}`);
            const data = await res.json();
            if (data.success) {
                const newStatus = data.data;
                const oldPhase = type === 'gold' ? this.lastTradingPhase : this.lastFundTradingPhase;
                const newPhase = newStatus.trading_phase;
                if (oldPhase && oldPhase !== newPhase) {
                    let eventMap = type === 'gold' ? {
                        'day_auction_day_session': { name: '日间交易开始', icon: '☀️' },
                        'day_session_closed': { name: '日间交易结束', icon: '🌅' },
                        'night_auction_night_session': { name: '夜间交易开始', icon: '🌙' },
                        'night_session_closed': { name: '夜间交易结束', icon: '🌃' }
                    } : {
                        'closed_trading': { name: '基金市场开盘', icon: '📈' },
                        'trading_lunch_break': { name: '基金午间休市', icon: '🌅' },
                        'lunch_break_trading': { name: '基金下午开盘', icon: '📈' },
                        'trading_closed': { name: '基金市场收盘', icon: '📉' }
                    };
                    const eventKey = `${oldPhase}_${newPhase}`;
                    if (this.settings.trading_events_enabled && eventMap[eventKey]) {
                        const event = eventMap[eventKey];
                        this.showTradingNotification(`${type === 'gold' ? '黄金' : '基金'} ${event.name}`, event.icon);
                    }
                }
                if (type === 'gold') { this.tradingStatus = newStatus; this.lastTradingPhase = newPhase; this.adjustPollingInterval(); }
                else { this.fundTradingStatus = newStatus; this.lastFundTradingPhase = newPhase; this.adjustFundPollingInterval(); }
            }
        },
        showTradingNotification(eventName, icon) {
            if ('Notification' in window && Notification.permission === 'granted') {
                new Notification(eventName.includes('黄金') ? 'Au99.99 交易提醒' : (eventName.includes('基金') ? '基金估值 交易提醒' : '交易状态提醒'), {
                    body: `${icon} ${eventName}`,
                    icon: '/favicon.ico',
                    requireInteraction: true
                });
            }
            this.showToast(`${icon} ${eventName}`, 'info');
        },
        startPricePolling() {
            if (this.priceTimer) clearInterval(this.priceTimer);
            const interval = this.tradingStatus.is_trading_time ? 5000 : 300000;
            this.fetchPrice();
            this.priceTimer = setInterval(() => { this?.fetchPrice?.(); }, interval);
            console.log(`[轮询] 黄金价格采集间隔已设置为 ${interval / 1000} 秒`);
        },
        startFundPolling() {
            if (this.fundTimer) clearInterval(this.fundTimer);
            const interval = this.fundTradingStatus.is_trading_time ? 3000 : 300000;
            this.fetchFunds(true);
            this.fetchHoldings(true, true);
            this.fundTimer = setInterval(() => { this.fetchFunds(true); this.fetchHoldings(true, true); }, interval);
            console.log(`[轮询] 基金数据采集间隔已设置为 ${interval / 1000} 秒`);
        },
        adjustPollingInterval() {
            if (this.currentView !== 'gold') return;
            const newInterval = this.tradingStatus.is_trading_time ? 5000 : 300000;
            if (this.lastPriceInterval !== newInterval) { this.lastPriceInterval = newInterval; this.startPricePolling(); }
        },
        adjustFundPollingInterval() {
            if (this.currentView !== 'fund') return;
            const newInterval = this.fundTradingStatus.is_trading_time ? 3000 : 300000;
            if (this.lastFundInterval !== newInterval) { this.lastFundInterval = newInterval; this.startFundPolling(); }
        },
        formatCountdown(seconds, nextEventTime) {
            if (!seconds || seconds <= 0) return '00:00:00';
            const days = Math.floor(seconds / 86400);
            const hours = Math.floor((seconds % 86400) / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = seconds % 60;
            if (days >= 2) {
                if (nextEventTime) {
                    const date = new Date(nextEventTime);
                    return `${date.getMonth() + 1}月${date.getDate()}日`;
                }
                return `${days}天后`;
            } else if (days > 0) return `${days}天${hours}时`;
            else if (hours > 0) return `${hours}小时${minutes}分`;
            else if (minutes > 0) return `${minutes}分${secs}秒`;
            else return `${secs}秒后`;
        },
        showToast(message, type = 'info') {
            const toast = document.createElement('div');
            toast.className = `fixed top-20 left-1/2 transform -translate-x-1/2 z-[70] px-6 py-3 rounded-full shadow-lg text-sm font-medium animate-fade-in`;
            if (type === 'info') toast.className += ' bg-blue-500/90 text-white';
            else if (type === 'success') toast.className += ' bg-green-500/90 text-white';
            else if (type === 'warning') toast.className += ' bg-yellow-500/90 text-black';
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.5s'; setTimeout(() => toast.remove(), 500); }, 5000);
        },
        handleResize() {
            if (this.chartInstance) {
                this.chartInstance.options.layout.padding.right = window.innerWidth < 640 ? 80 : 130;
                this.chartInstance.update('none');
            }
        },
        processDataForChart(sortedData) {
            if (!sortedData || sortedData.length === 0) return [];
            const now = Date.now() / 1000;
            const maxGap = 600;
            let filteredData = [];
            if (this.chartViewMode === '30M') filteredData = sortedData.filter(item => item.timestamp > now - 1800);
            else {
                const bucketSize = 5 * 60;
                let buckets = {};
                let recentData = [];
                sortedData.forEach(item => {
                    const age = now - item.timestamp;
                    if (age <= 1800) recentData.push(item);
                    else {
                        const bucketKey = Math.floor(item.timestamp / bucketSize);
                        if (!buckets[bucketKey]) buckets[bucketKey] = { min: item, max: item };
                        else { if (item.price < buckets[bucketKey].min.price) buckets[bucketKey].min = item; if (item.price > buckets[bucketKey].max.price) buckets[bucketKey].max = item; }
                    }
                });
                let bucketList = Object.values(buckets).flatMap(b => b.min.timestamp === b.max.timestamp ? [b.min] : (b.min.timestamp < b.max.timestamp ? [b.min, b.max] : [b.max, b.min]));
                filteredData = [...bucketList, ...recentData].sort((a, b) => a.timestamp - b.timestamp);
            }
            let finalData = [];
            for (let i = 0; i < filteredData.length; i++) {
                if (i > 0 && (filteredData[i].timestamp - filteredData[i - 1].timestamp) > maxGap) finalData.push({ x: (filteredData[i - 1].timestamp + 1), y: null });
                finalData.push({ x: filteredData[i].timestamp, y: filteredData[i].price });
            }
            return finalData;
        },
        handleInputFocus(event) { if (event && event.target) event.target.select(); },
        handleInputBlur() { },
        resetToCurrent() { if (this.currentData.price > 0) this.buyPrice = this.currentData.price; },
        async fetchPrice() {
            try {
                const res = await fetch('/api/price');
                const data = await res.json();
                if (data.success) {
                    this.fetchError = null;
                    const now = Date.now() / 1000;
                    this.isConnected = (now - data.data.timestamp) <= 20;
                    this.checkAlerts(data.data.price);
                    if (!this.hasInitializedBuyPrice && data.data.price > 0) {
                        this.buyPrice = data.data.price;
                        if (this.settings.high === 0 && this.settings.low === 0) {
                            this.settings.high = parseFloat((data.data.price * 1.03).toFixed(2));
                            this.settings.low = parseFloat((data.data.price * 0.97).toFixed(2));
                            this.saveSettings();
                        }
                        this.hasInitializedBuyPrice = true;
                    }
                    const priceChanged = this.currentData.price !== data.data.price;
                    const timeChanged = this.currentData.timestamp !== data.data.timestamp;
                    this.currentData = data.data;
                    this.updateChartData(data.data);
                    if (priceChanged) {
                        if (this.priceAnimTimer) clearTimeout(this.priceAnimTimer);
                        this.priceAnimating = false;
                        this.$nextTick(() => {
                            this.priceAnimating = true;
                            this.priceAnimTimer = setTimeout(() => { this.priceAnimating = false; this.priceAnimTimer = null; }, 400);
                        });
                    }
                    if (timeChanged) {
                        if (this.timeAnimTimer) clearTimeout(this.timeAnimTimer);
                        this.timeAnimating = false;
                        this.$nextTick(() => {
                            this.timeAnimating = true;
                            this.timeAnimTimer = setTimeout(() => { this.timeAnimating = false; this.timeAnimTimer = null; }, 800);
                        });
                    }
                } else {
                    this.isConnected = false;
                    if (this.currentData.price === 0) this.fetchError = data.message || '获取数据失败';
                }
            } catch (e) {
                console.error(e);
                this.isConnected = false;
                if (this.currentData.price === 0) this.fetchError = '网络连接异常';
            } finally { this.isInitialLoading = false; }
        },
        async fetchHistory() {
            try {
                const res = await fetch('/api/history');
                const data = await res.json();
                if (data.success) {
                    this.historyData = data.data;
                    this.$nextTick(() => {
                        if (document.getElementById('priceChart') && !this.chartInstance) {
                            this.initChart();
                        }
                    });
                }
            } catch (e) { console.error(e); }
        },
        async fetchRecords() {
            try {
                const res = await fetch('/api/records');
                const data = await res.json();
                if (data.success) this.records = data.data;
            } catch (e) { console.error(e); }
        },
        async fetchSettings() {
            try {
                const res = await fetch('/api/settings');
                const data = await res.json();
                if (data.success) this.settings = data.settings;
            } catch (e) { console.error(e); }
        },
        resetAlertsToDefault() {
            if (this.currentData.price > 0) {
                this.settings.high = parseFloat((this.currentData.price * 1.03).toFixed(2));
                this.settings.low = parseFloat((this.currentData.price * 0.97).toFixed(2));
                this.saveSettings();
            }
        },
        async saveSettings() {
            if (this.settings.enabled && Notification.permission !== "granted") {
                const permission = await Notification.requestPermission();
                if (permission !== "granted") {
                    this.settings.enabled = false;
                    alert("需要浏览器通知权限才能开启预警，喵！");
                }
            }
            try { await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.settings) }); } catch (e) { console.error(e); }
        },
        checkAlerts(currentPrice) {
            if (!this.settings.enabled || currentPrice <= 0) return;
            const now = Date.now();
            const cooldown = 5 * 60 * 1000;
            if (now - this.lastNotifiedTime < cooldown) return;
            let msg = "";
            if (this.settings.high > 0 && currentPrice >= this.settings.high) msg = `📈 金价已涨至 ${currentPrice}，超过预警线 ${this.settings.high}`;
            else if (this.settings.low > 0 && currentPrice <= this.settings.low) msg = `📉 金价已跌至 ${currentPrice}，低于预警线 ${this.settings.low}`;
            if (msg) { this.sendNotification("金价提醒 (Au99.99)", msg); this.lastNotifiedTime = now; }
        },
        sendNotification(title, body) {
            if (Notification.permission === "granted") {
                new Notification(title, { body: body, icon: "https://p3.itc.cn/images01/20210712/f6d76a7f34034442a8656157834241e3.png" });
            }
        },
        openPrompt(title, placeholder = '') {
            return new Promise((resolve) => {
                this.modal = { visible: true, type: 'prompt', title: title, placeholder: placeholder, inputValue: '', confirmText: '确认记录', confirmButtonClass: 'bg-blue-600 hover:bg-blue-500 text-white shadow-blue-900/50', resolve: resolve };
                this.$nextTick(() => { if (this.$refs.modalInput) this.$refs.modalInput.focus(); });
            });
        },
        openConfirm(title, message, confirmText = '确定', confirmClass = 'bg-red-600 hover:bg-red-500 text-white shadow-red-900/50') {
            return new Promise((resolve) => {
                this.modal = { visible: true, type: 'confirm', title: title, message: message, confirmText: confirmText, confirmButtonClass: confirmClass, resolve: resolve };
            });
        },
        closeModal(result) {
            if (this.modal.resolve) {
                if (this.modal.type === 'prompt') this.modal.resolve(result ? this.modal.inputValue : null);
                else this.modal.resolve(result);
            }
            this.modal.visible = false;
            this.modal.resolve = null;
        },
        async recordPrice() {
            if (this.isRecording) return;
            this.isRecording = true;
            const payload = { price: this.currentData.price, buy_price: this.buyPrice, profit: this.currentProfit.rate, note: '' };
            try {
                const res = await fetch('/api/record', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                const data = await res.json();
                if (data.success) this.records.push(data.record);
            } catch (e) { console.error(e); }
            finally { this.isRecording = false; }
        },
        async clearRecords() {
            const confirmed = await this.openConfirm('确认清空', '确定要清空所有历史记录吗？此操作无法撤销。', '清空记录');
            if (!confirmed) return;
            try { await fetch('/api/records/clear', { method: 'POST' }); this.records = []; } catch (e) { console.error(e); }
        },
        exportCSV() {
            if (this.records.length === 0) return;
            let csvContent = "\ufeff时间,价格(元/克),买入成本,盈亏率(%)\n";
            this.records.forEach(r => { csvContent += `${r.time_str},${r.price},${r.buy_price},${r.profit}\n`; });
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.setAttribute("href", url);
            link.setAttribute("download", `gold_price_records_${new Date().toISOString().split('T')[0]}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        },
        exportHistoryCSV() {
            if (this.historyData.length === 0) return;
            let csvContent = "\ufeff时间,价格(元/克)\n";
            [...this.historyData].sort((a, b) => b.timestamp - a.timestamp).forEach(h => { csvContent += `${new Date(h.timestamp * 1000).toLocaleString()},${h.price}\n`; });
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.setAttribute("href", url);
            link.setAttribute("download", `gold_daily_history_${new Date().toISOString().split('T')[0]}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        },
        initChart() {
            const ctx = document.getElementById('priceChart').getContext('2d');
            if (this.chartInstance) this.chartInstance.destroy();
            const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
            const gridColor = isDark ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.06)';
            const tickColor = isDark ? 'rgba(255, 255, 255, 0.3)' : 'rgba(0, 0, 0, 0.5)';
            const tooltipBg = isDark ? '#1a1f2e' : '#ffffff';
            const tooltipBorder = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';
            this.chartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Au99.99',
                        data: this.processDataForChart(this.historyData),
                        borderColor: '#facc15',
                        borderWidth: 2.5,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: '#facc15',
                        pointHoverBorderWidth: 3,
                        tension: 0.3,
                        fill: true,
                        backgroundColor: (context) => {
                            const chart = context.chart;
                            const { ctx, chartArea } = chart;
                            if (!chartArea) return null;
                            const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                            gradient.addColorStop(0, 'rgba(250, 204, 21, 0.15)');
                            gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
                            return gradient;
                        },
                        spanGaps: false,
                        normalized: true,
                        parsing: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 600, easing: 'easeOutQuart' },
                    transitions: { active: { animation: { duration: 0 } } },
                    interaction: { intersect: false, mode: 'index' },
                    layout: { padding: { left: 10, right: window.innerWidth < 640 ? 80 : 130, top: 15, bottom: 15 } },
                    scales: {
                        x: {
                            type: 'linear',
                            position: 'bottom',
                            grid: { color: gridColor, drawBorder: false },
                            ticks: {
                                color: tickColor,
                                font: { family: 'JetBrains Mono', size: 10 },
                                callback: (val) => { const d = new Date(val * 1000); return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0'); },
                                maxRotation: 0,
                                autoSkip: true,
                                maxTicksLimit: 6
                            }
                        },
                        y: {
                            grid: { color: gridColor, drawBorder: false },
                            ticks: { color: tickColor, font: { family: 'JetBrains Mono', size: 10 }, callback: (val) => val.toFixed(2) }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            enabled: true,
                            backgroundColor: tooltipBg,
                            titleColor: '#94a3b8',
                            titleFont: { family: 'Inter', size: 11, weight: 'bold' },
                            bodyColor: isDark ? '#fff' : '#1e293b',
                            bodyFont: { family: 'JetBrains Mono', size: 14, weight: 'bold' },
                            padding: 12,
                            cornerRadius: 8,
                            borderColor: tooltipBorder,
                            borderWidth: 1,
                            displayColors: false,
                            callbacks: {
                                title: (items) => { const d = new Date(items[0].parsed.x * 1000); return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); },
                                label: (item) => `¥ ${item.parsed.y.toFixed(2)}`
                            }
                        }
                    }
                },
                plugins: [(() => {
                    const plugin = {
                        id: 'highLowMarkers',
                        hoveredTag: null,
                        tagBounds: { high: null, low: null },
                        boundCanvas: null,
                        mouseMoveHandler: null,
                        mouseLeaveHandler: null,
                        afterInit: (chart) => {
                            const canvas = chart.canvas;

                            if (plugin.boundCanvas && plugin.mouseMoveHandler && plugin.mouseLeaveHandler) {
                                plugin.boundCanvas.removeEventListener('mousemove', plugin.mouseMoveHandler);
                                plugin.boundCanvas.removeEventListener('mouseleave', plugin.mouseLeaveHandler);
                            }

                            plugin.boundCanvas = canvas;
                            plugin.mouseMoveHandler = (e) => {
                                const rect = canvas.getBoundingClientRect();
                                const x = e.clientX - rect.left;
                                const y = e.clientY - rect.top;

                                const chartRight = chart.chartArea.right;
                                if (x < chartRight) {
                                    if (plugin.hoveredTag !== null) {
                                        plugin.hoveredTag = null;
                                        canvas.style.cursor = 'default';
                                        chart.draw();
                                    }
                                    return;
                                }

                                let newHovered = null;
                                const bounds = plugin.tagBounds;

                                // 检测顺序：优先检测 high，如果价格相同则新状态设为 'both' 将由逻辑处理
                                if (bounds.both) {
                                    if (x >= bounds.both.x && x <= bounds.both.x + bounds.both.w && y >= bounds.both.y && y <= bounds.both.y + bounds.both.h) {
                                        newHovered = 'both';
                                    }
                                } else {
                                    if (bounds.high && x >= bounds.high.x && x <= bounds.high.x + bounds.high.w && y >= bounds.high.y && y <= bounds.high.y + bounds.high.h) {
                                        newHovered = 'high';
                                    } else if (bounds.low && x >= bounds.low.x && x <= bounds.low.x + bounds.low.w && y >= bounds.low.y && y <= bounds.low.y + bounds.low.h) {
                                        newHovered = 'low';
                                    }
                                }

                                if (newHovered !== plugin.hoveredTag) {
                                    plugin.hoveredTag = newHovered;
                                    canvas.style.cursor = newHovered ? 'pointer' : 'default';
                                    chart.draw();
                                }
                            };
                            plugin.mouseLeaveHandler = () => {
                                if (plugin.hoveredTag !== null) {
                                    plugin.hoveredTag = null;
                                    canvas.style.cursor = 'default';
                                    chart.draw();
                                }
                            };
                            canvas.addEventListener('mousemove', plugin.mouseMoveHandler);
                            canvas.addEventListener('mouseleave', plugin.mouseLeaveHandler);
                        },
                        beforeDestroy: (chart) => {
                            const canvas = plugin.boundCanvas || chart.canvas;
                            if (canvas && plugin.mouseMoveHandler) {
                                canvas.removeEventListener('mousemove', plugin.mouseMoveHandler);
                            }
                            if (canvas && plugin.mouseLeaveHandler) {
                                canvas.removeEventListener('mouseleave', plugin.mouseLeaveHandler);
                            }
                            if (canvas) {
                                canvas.style.cursor = 'default';
                            }
                            plugin.boundCanvas = null;
                            plugin.mouseMoveHandler = null;
                            plugin.mouseLeaveHandler = null;
                            plugin.hoveredTag = null;
                        },
                        afterDatasetsDraw: (chart) => {
                            const { ctx, chartArea: { right }, scales: { x, y } } = chart;
                            const dataset = chart.data.datasets[0].data;
                            const validData = dataset.filter(d => d.y !== null);
                            if (validData.length < 2) return;

                            const prices = validData.map(d => d.y);
                            const maxPrice = Math.max(...prices);
                            const minPrice = Math.min(...prices);

                            // 重置边界缓存
                            plugin.tagBounds = { high: null, low: null, both: null };

                            const drawLabel = (val, label, color, type, customY) => {
                                const point = validData.find(d => d.y === val);
                                if (!point) return;
                                const xPos = x.getPixelForValue(point.x);
                                const actualY = y.getPixelForValue(val);
                                const drawY = customY !== undefined ? customY : actualY;
                                const isHovered = plugin.hoveredTag === type || (type !== 'both' && plugin.hoveredTag === 'both');

                                ctx.save();
                                // 线条连接到实际价格点 yPos
                                ctx.strokeStyle = isHovered ? color.replace('0.8', '1') : color;
                                ctx.setLineDash([2, 4]);
                                ctx.lineWidth = isHovered ? 2 : 1;
                                ctx.beginPath();
                                ctx.moveTo(xPos, actualY);
                                ctx.lineTo(right + 5, drawY);
                                ctx.stroke();

                                ctx.setLineDash([]);
                                ctx.fillStyle = color;
                                ctx.beginPath();
                                ctx.arc(xPos, actualY, isHovered ? 4 : 3, 0, Math.PI * 2);
                                ctx.fill();
                                if (isHovered) {
                                    ctx.strokeStyle = '#fff';
                                    ctx.lineWidth = 1;
                                    ctx.stroke();
                                }

                                const text = `${label}: ${val.toFixed(2)}`;
                                const fontSize = isHovered ? 12 : 10;
                                ctx.font = `bold ${fontSize}px JetBrains Mono`;
                                const textMetrics = ctx.measureText(text);
                                const textWidth = textMetrics.width;
                                const bgWidth = textWidth + 12;
                                const bgHeight = isHovered ? 22 : 16;
                                const bgX = right + 5;
                                const bgY = drawY - bgHeight / 2;

                                plugin.tagBounds[type] = { x: bgX, y: bgY, w: bgWidth, h: bgHeight };

                                ctx.fillStyle = color;
                                this.drawRoundedRect(ctx, bgX, bgY, bgWidth, bgHeight, 4);
                                ctx.fill();

                                ctx.fillStyle = '#fff';
                                ctx.textAlign = 'center';
                                ctx.textBaseline = 'middle';
                                ctx.fillText(text, bgX + bgWidth / 2, drawY);
                                ctx.restore();
                            };

                            if (Math.abs(maxPrice - minPrice) < 0.001) {
                                // 价格完全相同，合并显示
                                drawLabel(maxPrice, 'H/L', '#d4a574', 'both');
                            } else {
                                let yMax = y.getPixelForValue(maxPrice);
                                let yMin = y.getPixelForValue(minPrice);

                                // 避让逻辑：如果两个标签太近，强制拉开距离
                                const minGap = 20;
                                if (Math.abs(yMax - yMin) < minGap) {
                                    const mid = (yMax + yMin) / 2;
                                    yMax = mid - minGap / 2;
                                    yMin = mid + minGap / 2;
                                }

                                drawLabel(maxPrice, 'H', 'rgba(239, 68, 68, 0.8)', 'high', yMax);
                                drawLabel(minPrice, 'L', 'rgba(34, 197, 94, 0.8)', 'low', yMin);
                            }
                        }
                    };
                    return plugin;
                })()]
            });
            this.applyChartRange();

            this.chartInitialized = true;
            this.chartAnimationPhase = 'initial';
            setTimeout(() => {
                if (this.chartAnimationPhase === 'initial') {
                    this.chartAnimationPhase = 'none';
                }
            }, 600);
        },
        drawRoundedRect(ctx, x, y, width, height, radius) {
            ctx.beginPath();
            ctx.moveTo(x + radius, y);
            ctx.lineTo(x + width - radius, y);
            ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
            ctx.lineTo(x + width, y + height - radius);
            ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
            ctx.lineTo(x + radius, y + height);
            ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
            ctx.lineTo(x, y + radius);
            ctx.quadraticCurveTo(x, y, x + radius, y);
            ctx.closePath();
        },
        updateChartData(newData) {
            if (!this.chartInstance) {
                if (document.getElementById('priceChart') && this.historyData.length > 0) this.initChart();
                return;
            }
            this.historyData.push(newData);
            const now = Date.now() / 1000;
            if (this.historyData.length > 1000) this.historyData = this.historyData.filter(h => h.timestamp > now - 86400);
            this.chartInstance.data.datasets[0].data = this.processDataForChart(this.historyData);
            this.applyChartRange();
            this.chartInstance.update('none');
        },
        async fetchFunds(fast = true) {
            try {
                const res = await fetch(`/api/funds?fast=${fast ? '1' : '0'}`);
                const data = await res.json();
                if (data.success) {
                    const newMap = new Map(data.data.map(f => [f.code, f]));
                    this.funds = data.data.map(newFund => {
                        const oldFund = this.funds.find(f => f.code === newFund.code);
                        let animating = oldFund ? oldFund.animating : false;
                        let changeType = oldFund ? oldFund.changeType : '';
                        if (oldFund && (oldFund.change !== newFund.change || oldFund.price !== newFund.price)) {
                            animating = true;
                            changeType = (newFund.change > oldFund.change || newFund.price > oldFund.price) ? 'up' : 'down';
                        }
                        return { ...newFund, animating: animating, changeType: changeType };
                    });
                    setTimeout(() => { this.funds.forEach(f => { f.animating = false; }); }, 1000);
                    this.isConnected = true;
                }
            } catch (e) { console.error(e); this.isConnected = false; }
        },
        async addFund() {
            if (!this.newFundCode || this.isAddingFund) return;
            this.isAddingFund = true;
            try {
                const res = await fetch('/api/funds/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: this.newFundCode }) });
                const data = await res.json();
                if (data.success) { this.newFundCode = ''; this.fetchFunds(false); }
                else await this.openConfirm('添加失败', data.message, '知道了', 'bg-gray-600');
            } catch (e) { console.error(e); }
            finally { this.isAddingFund = false; }
        },
        async deleteFund(code) {
            const confirmed = await this.openConfirm('确认移除', `确定不再关注基金 ${code} 吗？`, '移除', 'bg-red-600');
            if (!confirmed) return;
            try { await fetch(`/api/funds/${code}`, { method: 'DELETE' }); this.funds = this.funds.filter(f => f.code !== code); } catch (e) { console.error(e); }
        },
        async toggleHoldings(fund, force = false) {
            this.portfolioDrawer.fundName = fund.name;
            this.portfolioDrawer.fundCode = fund.code;
            if (!force) this.portfolioDrawer.holdings = [];
            if (!force) this.portfolioDrawer.meta = { weight_coverage: 0, contribution_available: false, confidence_label: '--', report_period: '', estimate_mode: 'none' };
            this.portfolioDrawer.visible = true;
            this.portfolioDrawer.loading = true;
            try {
                const url = `/api/funds/${fund.code}/portfolio` + (force ? '?refresh=true' : '');
                const res = await fetch(url);
                const data = await res.json();
                if (data.success) {
                    if (Array.isArray(data.data)) {
                        this.portfolioDrawer.holdings = data.data;
                        this.portfolioDrawer.meta = { weight_coverage: 0, contribution_available: false, confidence_label: '--', report_period: '', estimate_mode: 'none' };
                    } else {
                        this.portfolioDrawer.holdings = data.data.holdings || [];
                        this.portfolioDrawer.meta = data.data.meta || { weight_coverage: 0, contribution_available: false, confidence_label: '--', report_period: '', estimate_mode: 'none' };
                    }
                }
            } catch (e) { console.error("获取重仓股失败", e); }
            finally { this.portfolioDrawer.loading = false; }
        },
        closePortfolioDrawer() { this.portfolioDrawer.visible = false; },
        addFundToHoldings(fund) {
            this.holdingModal = { visible: true, isEdit: false, code: fund.code, costPrice: fund.price || '', shares: '', note: fund.name || '', saving: false };
        },
        isFundInHoldings(code) { return this.holdings.some(h => String(h.code) === String(code)); },
        async fetchHoldings(fast = true, background = false) {
            if (!background) this.isLoadingHoldings = true;
            try {
                const res = await fetch(`/api/holdings?fast=${fast ? '1' : '0'}`);
                const data = await res.json();
                if (data.success) {
                    if (this.holdings.length > 0) {
                        this.holdings = (data.data || []).map(newH => {
                            const oldH = this.holdings.find(o => o.code === newH.code);
                            let animating = oldH ? oldH.animating : false;
                            let changeType = oldH ? oldH.changeType : '';
                            if (oldH && (oldH.change !== newH.change || oldH.price !== newH.price)) {
                                animating = true;
                                changeType = (newH.change > oldH.change || newH.price > oldH.price) ? 'up' : 'down';
                            }
                            return { ...newH, animating: animating, changeType: changeType };
                        });
                        setTimeout(() => { this.holdings.forEach(h => { h.animating = false; }); }, 1000);
                    } else { this.holdings = data.data || []; }
                    this.holdingsSummary = data.summary || { total_cost: 0, total_value: 0, total_profit: 0, total_profit_rate: 0, count: 0 };
                    this.$nextTick(() => { this.updateHoldingsListHeight(); });
                    const newLastUpdate = data.last_update || '--';
                    const lastUpdateChanged = this.holdingsLastUpdate !== newLastUpdate;
                    this.holdingsLastUpdate = newLastUpdate;
                    if (this.currentView === 'fund' && this.holdings.length > 0) {
                        this.fundPriceAnimating = true;
                        setTimeout(() => { this.fundPriceAnimating = false; }, 600);
                    }
                    if (lastUpdateChanged && this.currentView === 'fund') {
                        if (this.fundTimeAnimTimer) clearTimeout(this.fundTimeAnimTimer);
                        this.fundTimeAnimating = false;
                        this.$nextTick(() => {
                            this.fundTimeAnimating = true;
                            this.fundTimeAnimTimer = setTimeout(() => { this.fundTimeAnimating = false; this.fundTimeAnimTimer = null; }, 800);
                        });
                    }
                } else { console.warn('加载持仓失败:', data.message); }
            } catch (e) { console.error('获取持仓数据失败', e); }
            finally { if (!background) this.isLoadingHoldings = false; }
        },
        openAddHoldingModal() { this.holdingModal = { visible: true, isEdit: false, code: '', costPrice: '', shares: '', note: '', saving: false }; },
        openEditHoldingModal(holding) { this.holdingModal = { visible: true, isEdit: true, code: holding.code, costPrice: holding.cost_price, shares: holding.shares, note: holding.note || '', saving: false }; },
        closeHoldingModal() { this.holdingModal.visible = false; },
        async saveHolding() {
            const { code, costPrice, shares, note } = this.holdingModal;
            const codeStr = String(code || '').trim();
            if (!codeStr || codeStr.length !== 6 || !/^\d{6}$/.test(codeStr)) { await this.openConfirm('输入错误', '请输入有效的6位基金代码', '知道了', 'bg-gray-600'); return; }
            if (!costPrice || costPrice <= 0) { await this.openConfirm('输入错误', '成本价必须大于0', '知道了', 'bg-gray-600'); return; }
            if (!shares || shares <= 0) { await this.openConfirm('输入错误', '份额必须大于0', '知道了', 'bg-gray-600'); return; }
            this.holdingModal.saving = true;
            try {
                const res = await fetch('/api/holdings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: codeStr, cost_price: costPrice, shares: shares, note: note }) });
                const data = await res.json();
                if (data.success) { this.closeHoldingModal(); this.fetchHoldings(false); }
                else await this.openConfirm('保存失败', data.message, '知道了', 'bg-gray-600');
            } catch (e) { console.error('保存持仓失败', e); }
            finally { this.holdingModal.saving = false; }
        },
        async deleteHolding(code) {
            const confirmed = await this.openConfirm('确认删除', `确定要删除该持仓记录吗？此操作无法撤销。`, '删除');
            if (!confirmed) return;
            try {
                const res = await fetch(`/api/holdings/${code}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) this.fetchHoldings(false);
                else await this.openConfirm('删除失败', data.message, '知道了', 'bg-gray-600');
            } catch (e) { console.error('删除持仓失败', e); }
        },
        setChartViewMode(mode) {
            if (!['30M', '1D'].includes(mode)) { console.error('无效的图表模式:', mode); return; }
            if (this.chartViewMode === mode) return;

            this.chartViewMode = mode;

            if (this.chartInstance) {
                this.chartInstance.data.datasets[0].data = this.processDataForChart(this.historyData);
                this.applyChartRange();
                this.chartInstance.update('none');
            }

            this.$nextTick(() => {
                this.chartAnimationPhase = 'switch';
                setTimeout(() => {
                    if (this.chartAnimationPhase === 'switch') {
                        this.chartAnimationPhase = 'none';
                    }
                }, 600);
            });
        },
        applyChartRange() {
            if (!this.chartInstance) return;
            const now = Date.now() / 1000;
            if (this.chartViewMode === '30M') { this.chartInstance.options.scales.x.min = now - 1800; this.chartInstance.options.scales.x.max = now; }
            else {
                const nowDate = new Date();
                const todayStart = new Date(nowDate.getFullYear(), nowDate.getMonth(), nowDate.getDate());
                this.chartInstance.options.scales.x.min = todayStart.getTime() / 1000;
                this.chartInstance.options.scales.x.max = now;
            }
        }
    },
    async mounted() {
        this.loadTheme();
        this.fetchHistory();
        this.fetchRecords();
        this.fetchSettings();
        this.fetchPrice();
        try { await this.fetchTradingStatus('gold'); await this.fetchTradingStatus('fund'); } catch (e) { console.error('获取交易状态失败:', e); }
        this.tradingTimer = setInterval(this.checkTradingEvents, 1000);
        this.startPricePolling();
        if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
        window.addEventListener('resize', this.handleResize);
        if (this.isFirstLoad && !this.isInitialLoading) {
            this.$nextTick(() => {
                setTimeout(() => { this.cardsAnimated = true; this.isFirstLoad = false; }, 1200);
            });
        }
    },
    beforeUnmount() {
        if (this.priceTimer) clearInterval(this.priceTimer);
        if (this.fundTimer) clearInterval(this.fundTimer);
        if (this.tradingTimer) clearInterval(this.tradingTimer);
        if (this.timeAnimTimer) clearTimeout(this.timeAnimTimer);
        if (this.fundTimeAnimTimer) clearTimeout(this.fundTimeAnimTimer);
        window.removeEventListener('resize', this.handleResize);
        if (this.chartInstance) { this.chartInstance.destroy(); this.chartInstance = null; }
    }
}).mount('#app');
