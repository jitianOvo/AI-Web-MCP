#define UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wininet.h>
#include <string>
#include <vector>
#include <cstdio>

#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "wininet.lib")
#pragma comment(lib, "advapi32.lib")

static HWND g_console = 0;
static HICON g_icon = 0;
static HWND g_msgwin = 0;
static const wchar_t* MSG_CLASS = L"GPTWebMCPMsgWindow";

static void ToggleConsoleVisible();
static void ShowTrayMenu();

static LRESULT CALLBACK MsgProc(HWND hwnd, UINT msg, WPARAM w, LPARAM l) {
  if (msg == WM_APP + 1) {
    if (l == WM_LBUTTONUP || l == WM_LBUTTONDBLCLK) {
      ToggleConsoleVisible();
    } else if (l == WM_RBUTTONUP) {
      ShowTrayMenu();
    }
    return 0;
  }
  if (msg == WM_DESTROY) PostQuitMessage(0);
  return DefWindowProcW(hwnd, msg, w, l);
}
static HANDLE g_child = 0;
static HANDLE g_mutex = 0;
static bool g_paused = false;
static bool g_shutdown = false;
static std::wstring g_root;
static std::wstring g_token;

static std::wstring ExeDir() {
    wchar_t buf[MAX_PATH];
    DWORD n = GetModuleFileNameW(0, buf, MAX_PATH);
    std::wstring p(buf, n);
    size_t pos = p.find_last_of(L"\\/");
    return pos == std::wstring::npos ? L"." : p.substr(0, pos);
}

static std::wstring ReadConfigToken() {
    std::wstring path = g_root + L"\\config\\config.json";
    FILE* f = _wfopen(path.c_str(), L"rb");
    if (!f) return L"";
    std::string raw;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0) raw.append(buf, n);
    fclose(f);
    // find "bridge_token":"..."
    std::string key = "\"bridge_token\":\"";
    size_t a = raw.find(key);
    if (a == std::string::npos) return L"";
    a += key.size();
    size_t b = raw.find('"', a);
    if (b == std::string::npos) return L"";
    std::string tok = raw.substr(a, b - a);
    std::wstring out;
    for (char c : tok) out += (wchar_t)(unsigned char)c;
    return out;
}

static std::wstring HttpRequest(const wchar_t* method, const wchar_t* path) {
    std::wstring out;
    HINTERNET inet = InternetOpenW(L"GPT-Web-MCP", INTERNET_OPEN_TYPE_PRECONFIG, 0, 0, 0);
    if (!inet) return out;
    std::wstring url = L"http://127.0.0.1:8765" + std::wstring(path);
    HINTERNET conn = InternetOpenUrlW(inet, url.c_str(), 0, 0,
        INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE, 0);
    if (!conn) { InternetCloseHandle(inet); return out; }
    if (method[0] == L'P') {
        std::wstring headers = L"X-Bridge-Token: " + g_token + L"\r\n";
        HttpSendRequestW(conn, headers.c_str(), (DWORD)-1L, 0, 0);
    }
    char buf[2048];
    DWORD rd = 0;
    while (InternetReadFile(conn, buf, sizeof(buf) - 1, &rd) && rd > 0) {
        buf[rd] = 0;
        out += std::wstring((wchar_t*)buf, (wchar_t*)buf + rd);
    }
    InternetCloseHandle(conn);
    InternetCloseHandle(inet);
    return out;
}

static bool HttpOk(const wchar_t* path) {
    std::wstring r = HttpRequest(L"GET", path);
    return r.find(L"\"bridge\":\"online\"") != std::wstring::npos;
}

static void Log(const wchar_t* fmt, ...) {
    if (!g_console) return;
    wchar_t line[1024];
    va_list ap;
    va_start(ap, fmt);
    _vsnwprintf_s(line, 1024, _TRUNCATE, fmt, ap);
    va_end(ap);
    SYSTEMTIME st;
    GetLocalTime(&st);
    wchar_t stamp[64];
    swprintf_s(stamp, 64, L"[%02d:%02d:%02d]", st.wHour, st.wMinute, st.wSecond);
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD w;
    std::wstring msg = std::wstring(stamp) + L" " + line + L"\n";
    WriteConsoleW(h, msg.c_str(), (DWORD)msg.size(), &w, 0);
}

static void StartBridge() {
    if (HttpOk(L"/api/status")) { Log(L"[Bridge] Already running"); return; }
    std::wstring python = g_root + L"\\runtime\\venv\\Scripts\\python.exe";
    if (GetFileAttributesW(python.c_str()) == INVALID_FILE_ATTRIBUTES) {
        python = L"python";
    }
    SetEnvironmentVariableW(L"PYTHONPATH", (g_root + L"\\src").c_str());
    std::wstring cmd = L"\"" + python + L"\" -m gpt_web_mcp.bridge";
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    ZeroMemory(&pi, sizeof(pi));
    if (CreateProcessW(0, &cmd[0], 0, 0, FALSE, CREATE_NO_WINDOW, 0, g_root.c_str(), &si, &pi)) {
        g_child = pi.hProcess;
        CloseHandle(pi.hThread);
        Log(L"[Bridge] Started");
    } else {
        Log(L"[Bridge] Start failed");
    }
}

static void StopBridge(bool graceful) {
    if (graceful) {
        HttpRequest(L"POST", L"/api/shutdown");
        Sleep(1200);
    }
    if (g_child) {
        if (WaitForSingleObject(g_child, 0) == WAIT_TIMEOUT) {
            TerminateProcess(g_child, 0);
        }
        CloseHandle(g_child);
        g_child = 0;
    }
    Log(L"[Bridge] Stopped");
}

static void TogglePause() {
    if (g_paused) {
        HttpRequest(L"POST", L"/api/resume");
        g_paused = false;
        Log(L"[Service] Resumed");
    } else {
        HttpRequest(L"POST", L"/api/pause");
        g_paused = true;
        Log(L"[Service] Paused");
    }
}

static void ShowConsole(bool show) {
    if (!g_console) g_console = GetConsoleWindow();
    if (show) {
        ShowWindow(g_console, SW_SHOW);
        SetForegroundWindow(g_console);
    } else {
        ShowWindow(g_console, SW_HIDE);
    }
}

static void UpdateTray() {
    NOTIFYICONDATAW nid;
    ZeroMemory(&nid, sizeof(nid));
    nid.cbSize = sizeof(nid);
    nid.hWnd = g_msgwin;
    nid.uID = 1;
    nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    nid.uCallbackMessage = WM_APP + 1;
    nid.hIcon = g_icon;
    wcscpy_s(nid.szTip, L"GPT Web MCP");
    Shell_NotifyIconW(NIM_ADD, &nid);
    Shell_NotifyIconW(NIM_SETVERSION, &nid);
}

static void RemoveTray() {
    NOTIFYICONDATAW nid;
    ZeroMemory(&nid, sizeof(nid));
    nid.cbSize = sizeof(nid);
    nid.hWnd = g_msgwin;
    nid.uID = 1;
    Shell_NotifyIconW(NIM_DELETE, &nid);
}

static void ToggleConsoleVisible() {
    ShowConsole(!(IsWindowVisible(g_console) != 0));
}

static void ShowTrayMenu() {
    HMENU menu = CreatePopupMenu();
    AppendMenuW(menu, MF_STRING, 1, L"显示 / 隐藏控制台");
    AppendMenuW(menu, MF_STRING, 2, g_paused ? L"启动（恢复）" : L"暂停");
    AppendMenuW(menu, MF_SEPARATOR, 0, 0);
    AppendMenuW(menu, MF_STRING, 3, L"关闭");
    POINT pt;
    GetCursorPos(&pt);
    SetForegroundWindow(g_msgwin);
    UINT sel = TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, pt.x, pt.y, 0, g_msgwin, 0);
    DestroyMenu(menu);
    if (sel == 1) ToggleConsoleVisible();
    else if (sel == 2) TogglePause();
    else if (sel == 3) { g_shutdown = true; }
}

static BOOL WINAPI ConsoleHandler(DWORD ev) {
    if (ev == CTRL_CLOSE_EVENT) {
        ShowConsole(false);
        return TRUE;  // keep running in tray
    }
    return FALSE;
}

static void PollStatus() {
    std::wstring r = HttpRequest(L"GET", L"/api/status");
    if (r.empty()) { Log(L"[Status] bridge offline"); return; }
    bool ext = r.find(L"\"extension\":\"connected\"") != std::wstring::npos;
    bool page = r.find(L"\"page\":\"ready\"") != std::wstring::npos;
    bool streaming = r.find(L"\"response_state\":\"streaming\"") != std::wstring::npos;
    if (ext && page) Log(L"[Status] Extension connected, page ready%s", streaming ? L", streaming" : L"");
    else if (ext) Log(L"[Status] Extension connected, page not ready");
    else Log(L"[Status] Extension not connected");
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE, PWSTR, int) {
    g_root = ExeDir();
    size_t slash = g_root.rfind(L'\\');
    if (slash != std::wstring::npos) g_root = g_root.substr(0, slash);  // build\ -> project root
    g_token = ReadConfigToken();

    g_mutex = CreateMutexW(0, TRUE, L"GPT-Web-MCP-SingleInstance");
    if (g_mutex && GetLastError() == ERROR_ALREADY_EXISTS) {
        HWND other = FindWindowW(L"ConsoleWindowClass", 0);
        if (other) { ShowWindow(other, SW_SHOW); SetForegroundWindow(other); }
        return 0;
    }

    g_console = GetConsoleWindow();
    SetConsoleTitleW(L"GPT Web MCP");
    std::wstring ico = g_root + L"\\res\\GPT_Web_MCP_iconic.ico";
    g_icon = (HICON)LoadImageW(0, ico.c_str(), IMAGE_ICON, 32, 32, LR_LOADFROMFILE);
    if (!g_icon) g_icon = LoadIconW(0, IDI_APPLICATION);
    SendMessageW(g_console, WM_SETICON, ICON_BIG, (LPARAM)g_icon);
    SendMessageW(g_console, WM_SETICON, ICON_SMALL, (LPARAM)g_icon);

    WNDCLASSW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc = MsgProc;
    wc.hInstance = hInst;
    wc.lpszClassName = MSG_CLASS;
    RegisterClassW(&wc);
    g_msgwin = CreateWindowExW(0, MSG_CLASS, L"GPT Web MCP", 0, 0, 0, 0, 0,
        HWND_MESSAGE, 0, hInst, 0);

    SetConsoleCtrlHandler(ConsoleHandler, TRUE);
    UpdateTray();
    Log(L"[MCP] On-demand via Codex (stdio); Bridge auto-starting");
    StartBridge();

    SetTimer(g_console, 1, 5000, 0);
    MSG msg;
    while (GetMessageW(&msg, 0, 0, 0)) {
        if (msg.message == WM_TIMER && msg.wParam == 1 && !g_shutdown) PollStatus();
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
        if (g_shutdown) {
            StopBridge(true);
            RemoveTray();
            PostQuitMessage(0);
        }
    }

    RemoveTray();
    if (g_icon) DestroyIcon(g_icon);
    if (g_mutex) CloseHandle(g_mutex);
    return 0;
}
