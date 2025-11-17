// --- Utility Functions (equivalent to React hooks/helpers) ---

/**
 * Converts bytes to human-readable format.
 */
const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = 2;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
};

/**
 * Converts seconds to a human-readable uptime string.
 */
const formatUptime = (seconds) => {
    const days = Math.floor(seconds / (3600 * 24));
    seconds -= days * 3600 * 24;
    const hours = Math.floor(seconds / 3600);
    seconds -= hours * 3600;
    const minutes = Math.floor(seconds / 60);
    
    let result = '';
    if (days > 0) result += `${days}d `;
    if (hours > 0) result += `${hours}h `;
    result += `${minutes}m`;
    return result.trim();
};

/**
 * Central state management.
 */
let state = {
    isAuthenticated: false,
    currentPage: 'metrics',
    metrics: {},
    files: [],
    minecraftStatus: { status: 'loading', version: '', players: 0, uptime_h: 0 },
    terminalOutput: "Welcome to Aurora-cloud Terminal.\nType 'help' for available commands.\n$ ",
    ws: null,
    loading: {
        metrics: true,
        files: true,
        minecraft: true
    }
};

// Polling interval tracker
let metricsInterval = null;
let minecraftInterval = null;

// --- Icon SVGs (Inline Lucide icons) ---
const icons = {
    LayoutDashboard: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-layout-dashboard"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="3" y="14" rx="1"/><rect width="7" height="5" x="14" y="14" rx="1"/></svg>',
    HardDrive: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-hard-drive"><line x1="22" x2="2" y1="12" y2="12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.3 3H7.7a2 2 0 0 0-2.25 2.11z"/><line x1="6" x2="6.01" y1="16" y2="16"/><line x1="10" x2="10.01" y1="16" y2="16"/></svg>',
    Power: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-power"><path d="M12 2v10"/><path d="M18.4 12.68a9 9 0 1 1-12.8 0"/></svg>',
    Terminal: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-terminal"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>',
    Cpu: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-cpu"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M20 15h2"/><path d="M15 4h-2"/><path d="M15 20h-2"/><path d="M4 15v-2"/><path d="M20 15v-2"/></svg>',
    Server: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-server"><rect width="20" height="8" x="2" y="2" rx="2" ry="2"/><rect width="20" height="8" x="2" y="14" rx="2" ry="2"/><line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/></svg>',
    Zap: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-zap"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
    Database: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-database"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/><path d="M3 19a9 3 0 0 0 18 0"/></svg>',
    RefreshCcw: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-refresh-ccw"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-4 1"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 4-1"/><polyline points="8 17 4 13 8 9"/><polyline points="16 7 20 11 16 15"/></svg>',
    Users: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-users"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    Folder: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-folder"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 4 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/></svg>',
    FileText: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-file-text"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>',
    Play: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-play"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
    Pause: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" class="lucide lucide-pause"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>',
};

/**
 * Simple function to create an SVG icon with Tailwind classes.
 */
function createIcon(iconName, className = '') {
    const svgString = icons[iconName] || '';
    // Insert the desired classes directly into the SVG tag
    return svgString.replace(/class="lucide [^"]*"/, `class="lucide ${iconName.toLowerCase()} ${className}"`);
}

// --- Mock API Implementation (replicated from React version) ---
const api = {
    // Auth
    login: async (username, password) => {
        await new Promise(resolve => setTimeout(resolve, 500));
        if (username === 'root' && password === 'ChangeMeNow!') {
            return { success: true, token: "mock_jwt_token_12345" };
        }
        throw new Error("Invalid credentials");
    },
    // Server Status & Metrics
    fetchMetrics: async () => {
        await new Promise(resolve => setTimeout(resolve, 200));
        // FIX: Returning raw numbers instead of strings from toFixed()
        return {
            uptime: Math.floor(Math.random() * 86400) + 3600,
            cpu_load: (Math.random() * 0.4 + 0.1), // Now a number
            ram_used_gb: (Math.random() * 10 + 6), // Now a number
            ram_total_gb: 32.0,
            disk_used_gb: 75.2,
            disk_total_gb: 500.0,
            temp_c: (Math.random() * 10 + 50), // Now a number
        };
    },
    // File Management
    fetchFiles: async (path = '/') => {
        await new Promise(resolve => setTimeout(resolve, 300));
        return [
            { name: 'Documents', type: 'folder', size: 0, lastModified: '2025-11-15' },
            { name: 'logs', type: 'folder', size: 0, lastModified: '2025-11-17' },
            { name: 'config.yaml', type: 'file', size: 1520, lastModified: '2025-11-10' },
            { name: 'backup_2025.zip', type: 'file', size: 1048576000, lastModified: '2025-11-17' },
        ];
    },
    // Minecraft Control
    fetchMinecraftStatus: async () => {
        await new Promise(resolve => setTimeout(resolve, 200));
        const statuses = ['running', 'stopped'];
        const status = statuses[Math.floor(Math.random() * statuses.length)];
        return {
            status: status,
            version: "1.20.4",
            players: status === 'running' ? Math.floor(Math.random() * 5) : 0,
            uptime_h: status === 'running' ? Math.floor(Math.random() * 100) : 0,
        };
    },
    // Terminal (WebSocket simulation)
    connectTerminal: (onMessage) => {
        console.log("Simulating WebSocket connection...");
        const terminalOutput = [
            "Welcome to Aurora-cloud Terminal.",
            "Type 'help' for available commands.",
            "$ ls -la",
            "total 40",
            "drwxr-xr-x 4 root root 4096 Nov 17 19:20 .",
            "drwxr-xr-x 24 root root 4096 Nov 17 19:20 ..",
            "drwxr-xr-x 2 user user 4096 Nov 15 10:30 storage",
            " -rw-r--r-- 1 root root 1520 Nov 10 12:00 caddyfile.conf",
            "$ ",
        ];
        let index = 0;
        const interval = setInterval(() => {
            if (index < terminalOutput.length) {
                onMessage(terminalOutput[index++] + '\n');
            }
        }, 150);

        return {
            send: (command) => {
                onMessage(`> ${command}\n`);
                if (command.toLowerCase() === 'help') {
                    onMessage("Available commands: status, files, exit\n");
                } else if (command.toLowerCase() === 'exit') {
                    clearInterval(interval);
                    onMessage("Connection closed.\n");
                } else {
                    onMessage("Command not recognized.\n");
                }
                onMessage("$ ");
            },
            close: () => {
                clearInterval(interval);
                console.log("Simulated WebSocket closed.");
            }
        };
    }
};

// --- Component Renderers (functions generate HTML strings) ---

function renderMetricCard(iconName, title, value, unit, color = 'text-sky-400') {
    return `
        <div class="p-4 bg-gray-800/70 border border-gray-700 rounded-xl shadow-lg hover:shadow-xl transition duration-300">
            ${createIcon(iconName, `w-6 h-6 ${color}`)}
            <p class="mt-2 text-sm font-medium text-gray-400">${title}</p>
            <p class="text-2xl font-semibold mt-1">
                ${value}
                <span class="text-base font-light text-gray-500 ml-1">${unit}</span>
            </p>
        </div>
    `;
}

function renderProgressBar(value, max, label) {
    // Use parseFloat() defensively to ensure value and max are numbers
    const numValue = parseFloat(value);
    const numMax = parseFloat(max);

    if (isNaN(numValue) || isNaN(numMax) || numMax === 0) {
         return `<div class="mt-4"><p class="text-red-400 text-sm">Invalid data for ${label}</p></div>`;
    }

    const percentage = ((numValue / numMax) * 100).toFixed(1);
    const color = numValue / numMax > 0.8 ? 'bg-red-500' : numValue / numMax > 0.6 ? 'bg-yellow-500' : 'bg-green-500';

    return `
        <div class="mt-4">
            <div class="flex justify-between text-sm font-medium text-gray-300">
                <span>${label}</span>
                <span>${percentage}%</span>
            </div>
            <div class="w-full bg-gray-700 rounded-full h-2.5 mt-1">
                <div class="${color} h-2.5 rounded-full transition-all duration-500" style="width: ${percentage}%"></div>
            </div>
            <p class="text-xs text-gray-500 mt-1">${numValue.toFixed(1)} / ${numMax.toFixed(1)} ${label.includes('Disk') ? 'GB' : 'GB'}</p>
        </div>
    `;
}

function renderSystemMetrics() {
    const metrics = state.metrics;
    const loading = state.loading.metrics;

    if (loading) {
        return '<div class="text-gray-400 text-center py-8">Loading System Data...</div>';
    }

    return `
        <div class="space-y-6">
            <h2 class="text-2xl font-bold text-white flex items-center">
                ${createIcon('LayoutDashboard', 'w-6 h-6 mr-2 text-indigo-400')}
                System Overview
            </h2>
            <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                ${renderMetricCard('Cpu', 'CPU Load', (metrics.cpu_load * 100).toFixed(1), '%', 'text-fuchsia-400')}
                ${renderMetricCard('Server', 'Uptime', formatUptime(metrics.uptime), '', 'text-cyan-400')}
                ${renderMetricCard('Zap', 'CPU Temp', metrics.temp_c.toFixed(1), '°C', 'text-red-400')}
                ${renderMetricCard('Database', 'Storage Used', metrics.disk_used_gb.toFixed(1), 'GB', 'text-emerald-400')}
                ${renderMetricCard('RefreshCcw', 'Load Avg (1min)', (Math.random() * 2 + 1).toFixed(2), '', 'text-amber-400')}
                ${renderMetricCard('Users', 'Active Sessions', 5, '', 'text-pink-400')}
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div class="p-6 bg-gray-800/70 border border-gray-700 rounded-xl shadow-lg">
                    <h3 class="text-xl font-semibold text-white mb-4">Resource Utilization</h3>
                    ${renderProgressBar(metrics.ram_used_gb, metrics.ram_total_gb, "Memory (RAM)")}
                    ${renderProgressBar(metrics.disk_used_gb, metrics.disk_total_gb, "Disk Space")}
                    <p class="mt-4 text-sm text-gray-500">
                        Metrics are updated every 5 seconds.
                    </p>
                </div>
                <!-- Placeholder for Grafana Embed -->
                <div class="p-6 bg-gray-800/70 border border-gray-700 rounded-xl shadow-lg flex items-center justify-center min-h-64">
                    <p class="text-gray-400 text-center">
                        <span class="text-indigo-400">Grafana Dashboard</span> embedding goes here.
                        <br /> (e.g., iframe link to \`100.69.68.70:3000\`)
                    </p>
                </div>
            </div>
        </div>
    `;
}

function renderFileManager() {
    const files = state.files;
    const loading = state.loading.files;
    const currentPath = '/'; // Static mock path for simplicity

    const fileRows = files.map(file => `
        <tr class="border-b border-gray-700/50 hover:bg-gray-700/50 transition-colors cursor-pointer">
            <td class="px-6 py-3 whitespace-nowrap text-sm font-medium text-white flex items-center">
                ${file.type === 'folder' ? createIcon('Folder', 'w-5 h-5 text-sky-400 mr-3') : createIcon('FileText', 'w-5 h-5 text-gray-400 mr-3')}
                ${file.name}
            </td>
            <td class="px-6 py-3 whitespace-nowrap text-sm text-gray-400">
                ${file.type === 'file' ? formatBytes(file.size) : '--'}
            </td>
            <td class="px-6 py-3 whitespace-nowrap text-sm text-gray-400">${file.lastModified}</td>
            <td class="px-6 py-3 whitespace-nowrap text-right text-sm font-medium">
                ${file.type === 'file' ? '<button class="text-indigo-400 hover:text-indigo-300 ml-4">Download</button>' : ''}
                <button class="text-red-400 hover:text-red-300 ml-4">Delete</button>
            </td>
        </tr>
    `).join('');

    return `
        <div class="space-y-6">
            <h2 class="text-2xl font-bold text-white flex items-center">
                ${createIcon('HardDrive', 'w-6 h-6 mr-2 text-indigo-400')}
                File Storage Manager
            </h2>

            <div class="bg-gray-800/70 border border-gray-700 rounded-xl shadow-lg p-4">
                <div class="flex justify-between items-center mb-4">
                    <p class="text-sm text-gray-400">
                        Current Path: <span class="font-mono text-white bg-gray-700/50 p-1 rounded-md">${currentPath}</span>
                    </p>
                    <div class="flex space-x-2">
                        <button class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition">Upload File</button>
                        <button onclick="fetchFiles()" class="p-2 text-gray-400 hover:text-white transition">
                            ${createIcon('RefreshCcw', 'w-5 h-5')}
                        </button>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-700">
                        <thead class="bg-gray-700/50">
                            <tr>
                                <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Name</th>
                                <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Size</th>
                                <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Last Modified</th>
                                <th scope="col" class="relative px-6 py-3"></th>
                            </tr>
                        </thead>
                        <tbody class="bg-gray-800/50 divide-y divide-gray-700/50">
                            ${loading ? `<tr><td colSpan="4" class="text-center py-6 text-gray-400">Loading files...</td></tr>` : files.length === 0 ? `<tr><td colSpan="4" class="text-center py-6 text-gray-400">No files found.</td></tr>` : fileRows}
                        </tbody>
                    </table>
                </div>
                <div class="mt-4 text-xs text-gray-500">
                    User Quota: 100 GB | Used: 1.2 GB (Mock Data)
                </div>
            </div>
        </div>
    `;
}

function renderMinecraftControl() {
    const status = state.minecraftStatus;
    const isLoading = status.status === 'loading';
    const isRunning = status.status === 'running';
    const statusColor = isLoading ? 'text-yellow-500' : isRunning ? 'text-green-500' : 'text-red-500';

    const consoleContent = isRunning 
        ? '[19:21:05 INFO] Player A joined the game\n[19:21:10 INFO] World saved.'
        : 'Awaiting server start...';

    return `
        <div class="space-y-6">
            <h2 class="text-2xl font-bold text-white flex items-center">
                ${createIcon('Power', 'w-6 h-6 mr-2 text-indigo-400')}
                Minecraft Server Control
            </h2>
            <div class="bg-gray-800/70 border border-gray-700 rounded-xl shadow-lg p-6">
                <div class="flex flex-wrap justify-between items-start">
                    <div class="mb-4 sm:mb-0">
                        <p class="text-xl font-semibold text-white">Server Status:
                            <span class="ml-2 font-bold uppercase ${statusColor}">
                                ${status.status}
                            </span>
                        </p>
                        <p class="text-sm text-gray-400 mt-1">Version: ${status.version || 'N/A'} | Players: ${status.players} | Uptime: ${status.uptime_h}h</p>
                    </div>
                    <div class="flex space-x-3">
                        <button
                            onclick="handleMinecraftAction('start')"
                            ${isRunning || isLoading ? 'disabled' : ''}
                            class="flex items-center px-4 py-2 text-sm font-medium rounded-lg transition disabled:opacity-50 ${isRunning || isLoading ? 'bg-gray-600' : 'bg-green-600 hover:bg-green-700 text-white'}"
                        >
                            ${createIcon('Play', 'w-4 h-4 mr-2')} Start
                        </button>
                        <button
                            onclick="handleMinecraftAction('stop')"
                            ${!isRunning || isLoading ? 'disabled' : ''}
                            class="flex items-center px-4 py-2 text-sm font-medium rounded-lg transition disabled:opacity-50 ${!isRunning || isLoading ? 'bg-gray-600' : 'bg-red-600 hover:bg-red-700 text-white'}"
                        >
                            ${createIcon('Pause', 'w-4 h-4 mr-2')} Stop
                        </button>
                    </div>
                </div>

                <div class="mt-6 border-t border-gray-700 pt-4">
                    <p class="text-lg font-semibold text-white mb-2">Live Console Tail</p>
                    <div class="bg-black text-xs text-green-400 font-mono h-40 p-3 rounded-lg overflow-y-scroll border border-gray-700">
                        <pre id="minecraft-console">
[19:20:00 INFO] Starting minecraft server version 1.20.4
[19:20:01 WARN] Failed to load properties from file: server.properties
[19:20:05 INFO] Preparing level "world"
[19:20:10 INFO] Done (5.02s)! For help, type "help"
${consoleContent}</pre>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderInteractiveTerminal() {
    // Note: The actual terminal logic is handled by updateTerminal() and handleTerminalCommand()

    return `
        <div class="space-y-6">
            <h2 class="text-2xl font-bold text-white flex items-center">
                ${createIcon('Terminal', 'w-6 h-6 mr-2 text-indigo-400')}
                Interactive Terminal
            </h2>
            <div class="bg-black border border-gray-700 rounded-xl shadow-lg h-96 flex flex-col">
                <div
                    id="terminal-output"
                    class="flex-grow p-4 overflow-y-scroll text-sm font-mono text-lime-400 whitespace-pre-wrap"
                >${state.terminalOutput}</div>
                <div class="flex items-center p-3 border-t border-gray-700">
                    <span class="text-indigo-400 font-bold mr-2">$</span>
                    <input
                        type="text"
                        id="terminal-input"
                        onkeydown="if(event.key === 'Enter') handleTerminalCommand(event)"
                        class="flex-grow bg-transparent text-white focus:outline-none font-mono"
                        placeholder="Type command and press Enter..."
                        autofocus
                    />
                </div>
            </div>
            <p class="text-xs text-gray-500">
                Live shell access via WebSocket (Simulated). Use with caution.
            </p>
        </div>
    `;
}

// --- Core Application Logic ---

const navigation = [
    { name: 'System Metrics', icon: 'LayoutDashboard', page: 'metrics', subtitle: 'View and manage your server status and resources.' },
    { name: 'File Manager', icon: 'HardDrive', page: 'files', subtitle: 'Access, upload, and manage your storage files securely.' },
    { name: 'Minecraft Control', icon: 'Power', page: 'minecraft', subtitle: 'Start, stop, and monitor your dedicated Minecraft server.' },
    { name: 'Interactive Terminal', icon: 'Terminal', page: 'terminal', subtitle: 'Execute system commands in a live, interactive shell.' },
];

/**
 * Main function to re-render the application based on state.
 */
function renderApp() {
    const mainContentEl = document.getElementById('main-content');
    const pageTitleEl = document.getElementById('page-title');
    const pageSubtitleEl = document.getElementById('page-subtitle');
    
    const currentPageData = navigation.find(item => item.page === state.currentPage);
    
    pageTitleEl.textContent = currentPageData.name;
    pageSubtitleEl.textContent = currentPageData.subtitle;

    // Stop all existing polling/websockets
    clearInterval(metricsInterval);
    clearInterval(minecraftInterval);
    if (state.ws) {
        state.ws.close();
        state.ws = null;
    }

    // Render the page content and set up necessary listeners/polling
    switch (state.currentPage) {
        case 'metrics':
            mainContentEl.innerHTML = renderSystemMetrics();
            startMetricsPolling();
            break;
        case 'files':
            mainContentEl.innerHTML = renderFileManager();
            fetchFiles();
            break;
        case 'minecraft':
            mainContentEl.innerHTML = renderMinecraftControl();
            startMinecraftPolling();
            break;
        case 'terminal':
            mainContentEl.innerHTML = renderInteractiveTerminal();
            connectTerminal();
            break;
        default:
            mainContentEl.innerHTML = renderSystemMetrics();
            startMetricsPolling();
    }
}

/**
 * Initializes the sidebar navigation elements.
 */
function initNavigation() {
    const navListEl = document.getElementById('nav-list');
    navListEl.innerHTML = navigation.map(item => `
        <button
            data-page="${item.page}"
            onclick="setPage('${item.page}')"
            class="flex items-center w-full px-4 py-3 rounded-xl transition duration-200 text-left text-gray-400 hover:bg-gray-700/50 hover:text-white"
        >
            ${createIcon(item.icon, 'w-5 h-5 mr-3')}
            ${item.name}
        </button>
    `).join('');

    updateActiveNavLink();
}

/**
 * Updates the active class on the navigation links.
 */
function updateActiveNavLink() {
    document.querySelectorAll('#nav-list button').forEach(button => {
        const isActive = button.getAttribute('data-page') === state.currentPage;
        button.classList.toggle('bg-indigo-600/70', isActive);
        button.classList.toggle('text-white', isActive);
        button.classList.toggle('font-semibold', isActive);
        button.classList.toggle('shadow-md', isActive);
        button.classList.toggle('text-gray-400', !isActive);
        button.classList.toggle('hover:bg-gray-700/50', !isActive);
    });
}

/**
 * Changes the current page.
 */
window.setPage = function(page) {
    state.currentPage = page;
    updateActiveNavLink();
    renderApp();
}

// --- Data Fetching and Polling ---

async function fetchMetrics() {
    try {
        const data = await api.fetchMetrics();
        state.metrics = data;
        state.loading.metrics = false;
        if (state.currentPage === 'metrics') {
            renderApp(); // Force re-render of the current page to update metrics
        }
    } catch (error) {
        console.error("Failed to fetch metrics:", error);
        // Handle error state display if needed
    }
}

function startMetricsPolling() {
    fetchMetrics();
    metricsInterval = setInterval(fetchMetrics, 5000);
}

window.fetchFiles = async function() {
    try {
        state.loading.files = true;
        if (state.currentPage === 'files') { renderApp(); } // Show loading state
        const data = await api.fetchFiles();
        state.files = data;
        state.loading.files = false;
        if (state.currentPage === 'files') { renderApp(); } // Show data
    } catch (error) {
        console.error("Failed to fetch files:", error);
        state.loading.files = false;
        if (state.currentPage === 'files') { renderApp(); }
    }
}

async function fetchMinecraftStatus() {
    try {
        const data = await api.fetchMinecraftStatus();
        state.minecraftStatus = data;
        state.loading.minecraft = false;
        if (state.currentPage === 'minecraft') { renderApp(); }
    } catch (error) {
        console.error("Failed to fetch Minecraft status:", error);
        state.minecraftStatus = { status: 'error', version: 'N/A', players: 0, uptime_h: 0 };
        state.loading.minecraft = false;
        if (state.currentPage === 'minecraft') { renderApp(); }
    }
}

function startMinecraftPolling() {
    fetchMinecraftStatus();
    minecraftInterval = setInterval(fetchMinecraftStatus, 5000);
}

window.handleMinecraftAction = function(action) {
    // Optimistically update status to loading
    state.minecraftStatus = { ...state.minecraftStatus, status: 'loading' };
    renderApp();

    // Simulate API call delay
    setTimeout(() => {
        if (action === 'start') {
            state.minecraftStatus = { status: 'running', version: '1.20.4', players: 0, uptime_h: 0 };
        } else {
            state.minecraftStatus = { status: 'stopped', version: '1.20.4', players: 0, uptime_h: 0 };
        }
        renderApp();
    }, 1000);
}

// --- Terminal WebSocket and Command Logic ---

function updateTerminal(message) {
    state.terminalOutput += message;
    const outputEl = document.getElementById('terminal-output');
    if (outputEl) {
        outputEl.textContent = state.terminalOutput;
        // Auto-scroll
        outputEl.scrollTop = outputEl.scrollHeight;
    }
}

function connectTerminal() {
    if (state.ws) state.ws.close();
    state.ws = api.connectTerminal(updateTerminal);
    
    // Focus the input field when the terminal is rendered
    setTimeout(() => {
        const inputEl = document.getElementById('terminal-input');
        if (inputEl) inputEl.focus();
    }, 10);
}

window.handleTerminalCommand = function(event) {
    const inputEl = event.target;
    const command = inputEl.value.trim();
    inputEl.value = ''; // Clear input

    if (state.ws && command) {
        state.ws.send(command);
    }
}

// --- Auth & Initial Load ---

async function handleLogin(event) {
    event.preventDefault();
    const username = document.getElementById('username-input').value;
    const password = document.getElementById('password-input').value;
    const loginButton = document.getElementById('login-button');
    const errorEl = document.getElementById('login-error');

    loginButton.textContent = 'Logging In...';
    loginButton.disabled = true;
    errorEl.classList.add('hidden');

    try {
        await api.login(username, password);
        state.isAuthenticated = true;
        document.getElementById('login-container').classList.add('opacity-0');
        
        // Wait for fade out, then hide login and show app
        setTimeout(() => {
            document.getElementById('login-container').classList.add('hidden');
            document.getElementById('app-container').classList.remove('hidden');
            initNavigation();
            renderApp(); // Render the initial page (metrics)
        }, 500);

    } catch (error) {
        errorEl.textContent = error.message || 'Login failed.';
        errorEl.classList.remove('hidden');
        loginButton.textContent = 'Sign In';
        loginButton.disabled = false;
    }
}

window.handleSignOut = function() {
    if (state.ws) state.ws.close();
    clearInterval(metricsInterval);
    clearInterval(minecraftInterval);
    
    state.isAuthenticated = false;
    state.currentPage = 'metrics';
    document.getElementById('app-container').classList.add('hidden');
    
    const loginContainer = document.getElementById('login-container');
    loginContainer.classList.remove('hidden', 'opacity-0');
    
    // Reset form/button state
    document.getElementById('login-button').textContent = 'Sign In';
    document.getElementById('login-button').disabled = false;
    document.getElementById('login-error').classList.add('hidden');
    document.getElementById('username-input').value = '';
    document.getElementById('password-input').value = '';
}

window.onload = () => {
    // Attach login handler to the form
    document.getElementById('login-form').addEventListener('submit', handleLogin);
};