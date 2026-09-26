#define UNICODE
#include <windows.h>
#include <string>
#include <fstream>
#include <vector>

#pragma comment(lib, "user32.lib")

static void SendKey(WORD vk, bool down) {
    INPUT in;
    ZeroMemory(&in, sizeof(in));
    in.type = INPUT_KEYBOARD;
    in.ki.wVk = vk;
    in.ki.dwFlags = down ? 0 : KEYEVENTF_KEYUP;
    SendInput(1, &in, sizeof(in));
}

static void SendCtrlV() {
    SendKey(VK_CONTROL, true);
    SendKey(0x56, true);
    SendKey(0x56, false);
    SendKey(VK_CONTROL, false);
}

static void SendEnter() {
    SendKey(VK_RETURN, true);
    SendKey(VK_RETURN, false);
}

static bool IsMsedgePid(DWORD pid) {
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return false;
    wchar_t path[MAX_PATH];
    DWORD n = MAX_PATH;
    bool ok = QueryFullProcessImageNameW(h, 0, path, &n) != 0;
    CloseHandle(h);
    if (!ok) return false;
    std::wstring p(path, n);
    size_t slash = p.find_last_of(L"\\/");
    std::wstring name = slash == std::wstring::npos ? p : p.substr(slash + 1);
    return name == L"msedge.exe" || name == L"chrome.exe";
}

static HWND FindTargetWindow() {
    struct Ctx { HWND found; };
    Ctx ctx = { 0 };
    EnumWindows([](HWND hwnd, LPARAM lp) -> BOOL {
        Ctx* ctx = (Ctx*)lp;
        if (ctx->found) return FALSE;
        if (!IsWindowVisible(hwnd)) return TRUE;
        wchar_t cls[128];
        GetClassNameW(hwnd, cls, 128);
        if (wcscmp(cls, L"Chrome_WidgetWin_1") != 0) return TRUE;
        DWORD pid = 0;
        GetWindowThreadProcessId(hwnd, &pid);
        if (!IsMsedgePid(pid)) return TRUE;
        wchar_t title[512];
        GetWindowTextW(hwnd, title, 512);
        std::wstring t(title);
        if (t.find(L"ChatGPT") != std::wstring::npos) { ctx->found = hwnd; return FALSE; }
        if (!ctx->found) ctx->found = hwnd;
        return TRUE;
    }, (LPARAM)&ctx);
    return ctx.found;
}

static HWND FindForegroundEdge() {
    HWND fg = GetForegroundWindow();
    if (!fg || !IsWindowVisible(fg)) return 0;
    wchar_t cls[128];
    GetClassNameW(fg, cls, 128);
    if (wcscmp(cls, L"Chrome_WidgetWin_1") != 0) return 0;
    DWORD pid = 0;
    GetWindowThreadProcessId(fg, &pid);
    return IsMsedgePid(pid) ? fg : 0;
}

static void ActivateWindow(HWND w) {
    if (IsIconic(w)) ShowWindow(w, SW_RESTORE);
    DWORD self = GetCurrentThreadId();
    DWORD target = GetWindowThreadProcessId(w, 0);
    AttachThreadInput(self, target, TRUE);
    SetForegroundWindow(w);
    BringWindowToTop(w);
    SetActiveWindow(w);
    AttachThreadInput(self, target, FALSE);
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 2) return 2;
    bool paste_only = false;
    std::wstring arg1 = L"";
    if (argc >= 2) arg1 = argv[1];
    if (arg1 == L"--paste") {
        paste_only = true;
    } else {
        FILE* f = _wfopen(arg1.c_str(), L"rb");
        if (!f) return 3;
        std::wstring text;
        wchar_t buf[4096];
        size_t n;
        while ((n = fread(buf, sizeof(wchar_t), 4096, f)) > 0) text.append(buf, n);
        fclose(f);
        if (text.empty()) return 3;
        if (!OpenClipboard(0)) return 4;
        EmptyClipboard();
        HGLOBAL h = GlobalAlloc(GMEM_MOVEABLE, (text.size() + 1) * sizeof(wchar_t));
        if (h) {
            wchar_t* dst = (wchar_t*)GlobalLock(h);
            wcscpy_s(dst, text.size() + 1, text.c_str());
            GlobalUnlock(h);
            SetClipboardData(CF_UNICODETEXT, h);
        }
        CloseClipboard();
    }
    HWND w = FindTargetWindow();
    if (!w) return 5;
    HWND fg = FindForegroundEdge();
    if (fg) w = fg;
    ActivateWindow(w);
    Sleep(350);
    SendCtrlV();
    if (!paste_only) {
        Sleep(350);
        SendEnter();
    }
    return 0;
}
