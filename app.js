const apiBaseUrl = `${window.location.origin}/api`

let charts = {};

function formatTimestamp(timestamp) {
    return new Date(timestamp * 1000).toLocaleTimeString();
}

async function fetchCurrentPrices() {
    try {
        const response = await fetch(`${apiBaseUrl}/current_price`);
        const data = await response.json();
        updateCurrentPrices(data);
    } catch (error) {
        console.error('Error fetching current prices:', error);
    }
}

function updateCurrentPrices(data) {
    const container = document.getElementById('currentPrices');
    container.innerHTML = '';
    
    for (const [ticker, priceData] of Object.entries(data)) {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <h2>${ticker}</h2>
            <p class="price">$${priceData.price?.toFixed(4) || 'N/A'}</p>
            <p class="timestamp">Last updated: ${priceData.timestamp ? formatTimestamp(priceData.timestamp) : 'N/A'}</p>
        `;
        container.appendChild(card);
    }
}

async function fetchHistoricalPrices() {
    try {
        const response = await fetch(`${apiBaseUrl}/prices`);
        const data = await response.json();
        updateCharts(data);
    } catch (error) {
        console.error('Error fetching historical prices:', error);
    }
}

function updateCharts(data) {
    const chartContainer = document.getElementById('chartContainer');
    chartContainer.innerHTML = '';

    for (const [ticker, priceData] of Object.entries(data)) {
        const chartDiv = document.createElement('div');
        chartDiv.className = 'card chart';
        chartDiv.innerHTML = `<canvas id="chart-${ticker}"></canvas>`;
        chartContainer.appendChild(chartDiv);

        const ctx = document.getElementById(`chart-${ticker}`).getContext('2d');
        const chartData = priceData.map(d => ({
            x: new Date(d.timestamp * 1000),
            y: d.price
        }));

        if (charts[ticker]) {
            charts[ticker].destroy();
        }

        charts[ticker] = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [{
                    label: ticker,
                    data: chartData,
                    borderColor: '#0066cc',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'minute'
                        }
                    },
                    y: {
                        beginAtZero: false
                    }
                }
            }
        });
    }
}

document.getElementById('toggleCharts').addEventListener('click', function() {
    const chartContainer = document.getElementById('chartContainer');
    const isHidden = chartContainer.style.display === 'none';
    chartContainer.style.display = isHidden ? 'block' : 'none';
    this.textContent = isHidden ? 'Hide Charts' : 'Show Charts';
    if (isHidden) {
        fetchHistoricalPrices();
    }
});

// Initial fetch and set up interval for updates
fetchCurrentPrices();
setInterval(fetchCurrentPrices, 1000); // Update every 5 seconds

let isLive = false;
let lastUpdateTime = null;

function updateStatus(status) {
    const statusIndicator = document.getElementById('statusIndicator');
    if (status === 'live') {
        statusIndicator.textContent = 'Live: Data updating in real-time';
        statusIndicator.className = 'status live';
        isLive = true;
    } else if (status === 'error') {
        statusIndicator.textContent = 'Error: Unable to fetch data';
        statusIndicator.className = 'status error';
        isLive = false;
    }
}

function updateLastUpdateTime() {
    lastUpdateTime = new Date();
    const statusIndicator = document.getElementById('statusIndicator');
    statusIndicator.textContent = `Live: Last updated at ${lastUpdateTime.toLocaleTimeString()}`;
}

async function fetchCurrentPrices() {
    try {
        const response = await fetch(`${apiBaseUrl}/current_price`);
        const data = await response.json();
        updateCurrentPrices(data);
        updateStatus('live');
        updateLastUpdateTime();
    } catch (error) {
        console.error('Error fetching current prices:', error);
        updateStatus('error');
    }
}

// Check if data is still live
setInterval(() => {
    if (isLive && lastUpdateTime) {
        const currentTime = new Date();
        const timeDiff = (currentTime - lastUpdateTime) / 1000; // in seconds
        if (timeDiff > 10) { // If last update was more than 10 seconds ago
            updateStatus('error');
        }
    }
}, 5000); // Check every 5 seconds

// Initial fetch and set up interval for updates
fetchCurrentPrices();
setInterval(fetchCurrentPrices, 5000); // Update every 5 seconds