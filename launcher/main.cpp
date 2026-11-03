#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wininet.h>
#include <string>
#include <cstdio>
#include "json_fields.h"

#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "wininet.lib")
#pragma comment(lib, "advapi32.lib")

static const wchar_t* MAIN_CLASS = L"AIWebMCPMainWindow";
static const wchar_t* MSG_CLASS = L"AIWebMCPMsgWindow";
static const int IDM_SHOW = 1;
static const int IDM_TOGGLE = 2;
static const int IDM_EXIT = 3;
static const int TRAY_ID = 1;
static const UINT WM_TRAY = WM_APP + 1;

static HWND g_main = 0;
static HWND g_msgwin = 0;
static HICON g_icon = 0;
static HANDLE g_child = 0;
static HANDLE g_mutex = 0;
static bool g_paused = false;
static bool g_force_exit = false;
static std::wstring g_root;
static std::wstring g_token;
static std::wstring g_host = L"127.0.0.1";
static INTERNET_PORT g_port = 8765;
static std::wstring g_status_error;
static std::wstring g_status_bridge = L"-";
static std::wstring g_status_ext = L"-";
static std::wstring g_status_page = L"-";
static std::wstring g_status_state = L"-";
static std::wstring g_status_target = L"-";
static HGLOBAL g_hText = 0;

static std::wstring ExeDir() {
    wchar_t buf[MAX_PATH];
    DWORD n = GetModuleFileNameW(0, buf, MAX_PATH);
    std::wstring p(buf, n);
    size_t pos = p.find_last_of(L"\\/");
    return pos == std::wstring::npos ? L"." : p.substr(0, pos);
}

static std::wstring Utf8Wide(const std::string& value) {
    if (value.empty()) return {};
    const int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), (int)value.size(), nullptr, 0);
    if (!count) return L"响应编码错误";
    std::wstring result(count, L'\0');
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value.data(), (int)value.size(), &result[0], count);
    return result;
}

static bool ReadConfig() {
    FILE* file = _wfopen((g_root + L"\\config\\config.json").c_str(), L"rb");
    if (!file) { g_status_error = L"配置文件不存在"; return false; }
    std::string raw;
    char buffer[4096];
    size_t count;
    while ((count = fread(buffer, 1, sizeof(buffer), file)) > 0) raw.append(buffer, count);
    fclose(file);
    g_token = Utf8Wide(JsonField(raw, "bridge_token"));
    const auto host = JsonField(raw, "host");
    g_host = host.empty() ? L"127.0.0.1" : Utf8Wide(host);
    g_port = JsonPort(raw);
    if (g_token.empty()) { g_status_error = L"配置缺少 bridge_token"; return false; }
    return true;
}

struct HttpReply { DWORD status = 0; std::string body; DWORD error = 0; };

static HttpReply HttpRequest(const wchar_t* method, const wchar_t* path) {
    HttpReply reply;
    HINTERNET session = InternetOpenW(L"AI-Web-MCP", INTERNET_OPEN_TYPE_DIRECT, nullptr, nullptr, 0);
    if (!session) { reply.error = GetLastError(); return reply; }
    DWORD timeout = 1500;
    InternetSetOptionW(session, INTERNET_OPTION_CONNECT_TIMEOUT, &timeout, sizeof(timeout));
    InternetSetOptionW(session, INTERNET_OPTION_RECEIVE_TIMEOUT, &timeout, sizeof(timeout));
    InternetSetOptionW(session, INTERNET_OPTION_SEND_TIMEOUT, &timeout, sizeof(timeout));
    HINTERNET connection = InternetConnectW(session, g_host.c_str(), g_port, nullptr, nullptr, INTERNET_SERVICE_HTTP, 0, 0);
    HINTERNET request = connection ? HttpOpenRequestW(connection, method, path, nullptr, nullptr, nullptr,
        INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE | INTERNET_FLAG_NO_AUTO_REDIRECT, 0) : nullptr;
    const std::wstring headers = L"X-Bridge-Token: " + g_token + L"\r\nContent-Type: application/json\r\n";
    if (request && HttpSendRequestW(request, headers.c_str(), (DWORD)headers.size(), nullptr, 0)) {
        DWORD length = sizeof(reply.status);
        HttpQueryInfoW(request, HTTP_QUERY_STATUS_CODE | HTTP_QUERY_FLAG_NUMBER, &reply.status, &length, nullptr);
        char buffer[8192];
        DWORD count;
        while (InternetReadFile(request, buffer, sizeof(buffer), &count) && count) reply.body.append(buffer, count);
    } else reply.error = GetLastError();
    if (request) InternetCloseHandle(request);
    if (connection) InternetCloseHandle(connection);
    InternetCloseHandle(session);
    return reply;
}

static bool HttpPost(const wchar_t* path) {
    const auto reply = HttpRequest(L"POST", path);
    if (reply.status != 200) {
        g_status_error = reply.status ? L"HTTP " + std::to_wstring(reply.status) : L"连接失败 " + std::to_wstring(reply.error);
        return false;
    }
    return true;
}

static bool BridgeOnline() {
    if (!ReadConfig()) return false;
    const auto reply = HttpRequest(L"GET", L"/api/status");
    return reply.status == 200 && JsonField(reply.body, "bridge") == "online";
}

static void RefreshStatus() {
    g_status_error.clear();
    g_status_bridge = L"离线";
    g_status_ext = L"未连接";
    g_status_page = L"未就绪";
    g_status_state = L"无任务";
    g_status_target = L"未绑定";
    if (!ReadConfig()) { g_status_bridge = L"配置异常"; return; }
    const auto reply = HttpRequest(L"GET", L"/api/status");
    if (reply.status != 200) {
        g_status_error = reply.status == 401 ? L"认证失败，请检查配置" :
            reply.status ? L"HTTP " + std::to_wstring(reply.status) : L"连接失败 " + std::to_wstring(reply.error);
        return;
    }
    if (JsonField(reply.body, "bridge") != "online") { g_status_error = L"状态响应缺少 bridge 字段"; return; }
    g_status_bridge = JsonField(reply.body, "paused") == "true" ? L"在线（已暂停）" : L"在线";
    g_paused = JsonField(reply.body, "paused") == "true";
    g_status_ext = JsonField(reply.body, "extension") == "connected" ? L"已连接" : L"未连接";
    g_status_page = JsonField(reply.body, "page") == "ready" ? L"就绪" : L"未就绪";
    const auto state = JsonField(reply.body, "response_state");
    g_status_state = state == "streaming" ? L"正在回答" : state == "waiting" ? L"等待回答" : L"空闲";
    const auto target = JsonField(reply.body, "target_id");
    if (!target.empty() && target != "unbound") g_status_target = Utf8Wide(target);
}

static void UpdateMainText(HWND hwnd) {
    std::wstring text =
        L"版本 1.1.1\r\n\r\n"
        L"桥服务: " + g_status_bridge + L"\r\n"
        L"扩展:   " + g_status_ext + L"\r\n"
        L"页面:   " + g_status_page + L"\r\n"
        L"任务:   " + g_status_state + L"\r\n"
        L"绑定:   " + g_status_target + L"\r\n\r\n" +
        (g_status_error.empty() ? L"" : L"诊断: " + g_status_error + L"\r\n\r\n") +
        L"关闭窗口只隐藏到托盘，服务继续运行。\r\n"
        L"右键托盘图标可显示窗口 / 开始·暂停 / 退出程序。";
    if (g_hText) GlobalFree(g_hText);
    size_t bytes = (text.size() + 1) * sizeof(wchar_t);
    g_hText = GlobalAlloc(GMEM_MOVEABLE, bytes);
    if (g_hText) {
        void* dst = GlobalLock(g_hText);
        if (dst) {
            memcpy(dst, text.c_str(), bytes);
            GlobalUnlock(g_hText);
        }
    }
    SetWindowTextW(hwnd, (L"AI Web MCP Bridge — " + g_status_bridge + L" / " + g_status_ext + L" / " + g_status_page + L" / " + g_status_target).c_str());
    InvalidateRect(hwnd, 0, TRUE);
}

static void StartBridge() {
    if (BridgeOnline()) return;
    std::wstring python = g_root + L"\\runtime\\venv\\Scripts\\python.exe";
    if (GetFileAttributesW(python.c_str()) == INVALID_FILE_ATTRIBUTES) {
        python = L"python";
    }
    SetEnvironmentVariableW(L"PYTHONPATH", (g_root + L"\\src").c_str());
    std::wstring cmd = L"\"" + python + L"\" -m ai_web_mcp.bridge";
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
    }
}

static void StopBridge(bool graceful) {
    if (graceful && !g_token.empty()) {
        HttpPost(L"/api/shutdown");
        Sleep(1200);
    }
    if (g_child) {
        if (WaitForSingleObject(g_child, 0) == WAIT_TIMEOUT) {
            TerminateProcess(g_child, 0);
        }
        CloseHandle(g_child);
        g_child = 0;
    }
}

static void ToggleService() {
    if (g_paused) {
        if (HttpPost(L"/api/resume")) g_paused = false;
    } else {
        bool online = BridgeOnline();
        if (!online) {
            StartBridge();
            Sleep(800);
        }
        if (HttpPost(L"/api/pause")) g_paused = true;
    }
    RefreshStatus();
    UpdateMainText(g_main);
}

static void ShowMainWindow(bool show) {
    if (!g_main) return;
    if (show) {
        ShowWindow(g_main, SW_SHOW);
        ShowWindow(g_main, SW_RESTORE);
        SetForegroundWindow(g_main);
    } else {
        ShowWindow(g_main, SW_HIDE);
    }
    RefreshStatus();
    UpdateMainText(g_main);
}

static void UpdateTrayIcon() {
    NOTIFYICONDATAW nid;
    ZeroMemory(&nid, sizeof(nid));
    nid.cbSize = sizeof(nid);
    nid.hWnd = g_msgwin;
    nid.uID = TRAY_ID;
    nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    nid.uCallbackMessage = WM_TRAY;
    nid.hIcon = g_icon;
    wcscpy_s(nid.szTip, L"AI Web MCP Bridge");
    Shell_NotifyIconW(NIM_ADD, &nid);
    Shell_NotifyIconW(NIM_SETVERSION, &nid);
}

static void RemoveTrayIcon() {
    NOTIFYICONDATAW nid;
    ZeroMemory(&nid, sizeof(nid));
    nid.cbSize = sizeof(nid);
    nid.hWnd = g_msgwin;
    nid.uID = TRAY_ID;
    Shell_NotifyIconW(NIM_DELETE, &nid);
}

static void ShowTrayMenu() {
    HMENU menu = CreatePopupMenu();
    bool main_visible = IsWindowVisible(g_main) != 0;
    AppendMenuW(menu, MF_STRING | (main_visible ? MF_CHECKED : 0), IDM_SHOW,
        main_visible ? L"显示窗口 ✓" : L"显示窗口");
    AppendMenuW(menu, MF_STRING | (g_paused ? 0 : MF_CHECKED), IDM_TOGGLE,
        g_paused ? L"开始服务" : L"暂停服务");
    AppendMenuW(menu, MF_SEPARATOR, 0, 0);
    AppendMenuW(menu, MF_STRING, IDM_EXIT, L"退出程序");
    POINT pt;
    GetCursorPos(&pt);
    SetForegroundWindow(g_msgwin);
    UINT sel = TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, pt.x, pt.y, 0, g_msgwin, 0);
    DestroyMenu(menu);
    if (sel == IDM_SHOW) {
        ShowMainWindow(!main_visible);
    } else if (sel == IDM_TOGGLE) {
        ToggleService();
    } else if (sel == IDM_EXIT) {
        g_force_exit = true;
        PostMessageW(g_msgwin, WM_DESTROY, 0, 0);
    }
}

static LRESULT CALLBACK MsgProc(HWND hwnd, UINT msg, WPARAM w, LPARAM l) {
    if (msg == WM_TRAY) {
        if (l == WM_LBUTTONUP || l == WM_LBUTTONDBLCLK) {
            ShowMainWindow(!(IsWindowVisible(g_main) != 0));
        } else if (l == WM_RBUTTONUP) {
            ShowTrayMenu();
        }
        return 0;
    }
    if (msg == WM_DESTROY) {
        // Always stop the child bridge on any destroy path (tray exit, system
        // shutdown, task-manager close) so the user keeps full control.
        StopBridge(true);
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, w, l);
}

static LRESULT CALLBACK MainProc(HWND hwnd, UINT msg, WPARAM w, LPARAM l) {
    switch (msg) {
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC dc = BeginPaint(hwnd, &ps);
            HBRUSH bg = CreateSolidBrush(RGB(245, 246, 250));
            FillRect(dc, &ps.rcPaint, bg);
            DeleteObject(bg);
            SetBkMode(dc, TRANSPARENT);
            HFONT font = CreateFontW(-16, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET,
                0, 0, CLEARTYPE_QUALITY, 0, L"Microsoft YaHei UI");
            HFONT title = CreateFontW(-22, 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET,
                0, 0, CLEARTYPE_QUALITY, 0, L"Microsoft YaHei UI");
            RECT rc;
            GetClientRect(hwnd, &rc);
            const wchar_t* head = L"AI Web MCP Bridge";
            rc.left += 16;
            rc.top += 6;
            HFONT old = (HFONT)SelectObject(dc, title);
            SetTextColor(dc, RGB(30, 60, 110));
            DrawTextW(dc, head, -1, &rc, DT_LEFT | DT_TOP | DT_NOPREFIX);
            rc.top += 34;
            SelectObject(dc, font);
            SetTextColor(dc, RGB(40, 45, 55));
            if (g_hText) {
                void* p = GlobalLock(g_hText);
                if (p) {
                    DrawTextW(dc, (const wchar_t*)p, -1, &rc, DT_LEFT | DT_TOP | DT_NOPREFIX | DT_WORDBREAK);
                    GlobalUnlock(g_hText);
                }
            }
            SelectObject(dc, old);
            DeleteObject(font);
            DeleteObject(title);
            EndPaint(hwnd, &ps);
            return 0;
        }
        case WM_CLOSE:
            ShowMainWindow(false);
            return 0;
    }
    return DefWindowProcW(hwnd, msg, w, l);
}

int APIENTRY wWinMain(HINSTANCE hInst, HINSTANCE, PWSTR commandLine, int) {
    g_root = ExeDir();
    size_t slash = g_root.rfind(L'\\');
    if (slash != std::wstring::npos) g_root = g_root.substr(0, slash);
    ReadConfig();
    if (std::wstring(commandLine) == L"--check-status") {
        RefreshStatus();
        const std::wstring report = L"桥服务: " + g_status_bridge + L"\n扩展: " + g_status_ext +
            L"\n页面: " + g_status_page + L"\n任务: " + g_status_state + L"\n绑定: " + g_status_target + L"\n诊断: " + g_status_error;
        const int count = WideCharToMultiByte(CP_UTF8, 0, report.data(), (int)report.size(), nullptr, 0, nullptr, nullptr);
        std::string bytes(count, '\0');
        WideCharToMultiByte(CP_UTF8, 0, report.data(), (int)report.size(), &bytes[0], count, nullptr, nullptr);
        CreateDirectoryW((g_root + L"\\tmp").c_str(), nullptr);
        FILE* output = _wfopen((g_root + L"\\tmp\\launcher-status.txt").c_str(), L"wb");
        if (!output) return 2;
        fwrite(bytes.data(), 1, bytes.size(), output);
        fclose(output);
        return g_status_error.empty() ? 0 : 1;
    }

    g_mutex = CreateMutexW(0, TRUE, L"AI-Web-MCP-SingleInstance");
    if (g_mutex && GetLastError() == ERROR_ALREADY_EXISTS) {
        HWND other = FindWindowW(MAIN_CLASS, 0);
        if (other) { ShowWindow(other, SW_SHOW); SetForegroundWindow(other); }
        return 0;
    }

    std::wstring ico = g_root + L"\\res\\AI_Web_MCP_iconic.ico";
    g_icon = (HICON)LoadImageW(0, ico.c_str(), IMAGE_ICON, 32, 32, LR_LOADFROMFILE);
    if (!g_icon) g_icon = (HICON)LoadImageW(hInst, MAKEINTRESOURCEW(1), IMAGE_ICON, 32, 32, 0);
    if (!g_icon) g_icon = LoadIconW(0, IDI_APPLICATION);

    WNDCLASSW wm;
    ZeroMemory(&wm, sizeof(wm));
    wm.lpfnWndProc = MainProc;
    wm.hInstance = hInst;
    wm.hIcon = g_icon;
    wm.lpszClassName = MAIN_CLASS;
    RegisterClassW(&wm);

    WNDCLASSW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc = MsgProc;
    wc.hInstance = hInst;
    wc.lpszClassName = MSG_CLASS;
    RegisterClassW(&wc);

    g_main = CreateWindowExW(0, MAIN_CLASS, L"AI Web MCP Bridge",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT, CW_USEDEFAULT, 520, 340, 0, 0, hInst, 0);
    g_msgwin = CreateWindowExW(0, MSG_CLASS, L"tray", 0, 0, 0, 0, 0,
        HWND_MESSAGE, 0, hInst, 0);

    UpdateTrayIcon();
    ShowMainWindow(true);
    StartBridge();

    SetTimer(g_msgwin, 2, 2000, 0);
    MSG msg;
    while (GetMessageW(&msg, 0, 0, 0)) {
        if (msg.message == WM_TIMER && msg.wParam == 2) {
            RefreshStatus();
            UpdateMainText(g_main);
        }
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    RemoveTrayIcon();
    if (g_icon) DestroyIcon(g_icon);
    if (g_hText) GlobalFree(g_hText);
    if (g_mutex) CloseHandle(g_mutex);
    return 0;
}
