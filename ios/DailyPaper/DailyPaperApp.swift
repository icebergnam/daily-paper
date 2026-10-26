import SwiftUI
import CoreText
import UniformTypeIdentifiers

// 데일리 페이퍼 읽기 전용 앱: Mac 대시보드가 iCloud Drive/DailyPaper/library.json에 내보낸 서재 데이터(library_data()와 같은 모양)를 읽는다.
@main struct DailyPaperApp: App {
    init() {  // 앱에 넣은 글꼴(예: Noto Serif KR)을 등록한다. 없으면 시스템 글꼴로 그린다
        for ext in ["ttf", "otf"] {
            for u in Bundle.main.urls(forResourcesWithExtension: ext, subdirectory: nil) ?? [] {
                CTFontManagerRegisterFontsForURL(u as CFURL, .process, nil)
            }
        }
    }

    var body: some Scene {
        WindowGroup { RootView() }
    }
}

struct Library: Decodable {
    var papers: [Paper]
    var keywords: [String]
    var issues: [Issue]
    var days: [String: Day]
    var synced: String?
    var period: Int?
    var schedule: String?

    struct Issue: Decodable, Hashable { var no: Int; var date: String }
    struct Day: Decodable { var found: Int; var notion: Bool }
}

struct Paper: Decodable, Identifiable, Hashable {
    var id, title, short, authors, authorShort: String
    var year: Int?
    var venue, kw: String
    var issue: Int
    var date, status, tldr: String
    var zotero: Bool
    var url, oa, notion: String
    var ev: [String]
    var table: [[String]]
    var isNew: Bool
}

@Observable final class Store {
    var lib: Library?
    var error: String?
    private let cache = URL.documentsDirectory.appending(path: "library.json")  // 마지막으로 읽은 것: iCloud에 닿지 않아도 연다

    init() {
        if let d = try? Data(contentsOf: cache) { lib = try? JSONDecoder().decode(Library.self, from: d) }
    }

    func pick(_ url: URL) async {
        let ok = url.startAccessingSecurityScopedResource()
        defer { if ok { url.stopAccessingSecurityScopedResource() } }
        UserDefaults.standard.set(try? url.bookmarkData(), forKey: "bookmark")
        await read(url)
    }

    func reload() async {
        guard let b = UserDefaults.standard.data(forKey: "bookmark") else { return }
        var stale = false
        guard let url = try? URL(resolvingBookmarkData: b, bookmarkDataIsStale: &stale) else {
            error = "서재 파일을 찾지 못했습니다. 파일을 다시 골라 주세요"
            return
        }
        let ok = url.startAccessingSecurityScopedResource()
        defer { if ok { url.stopAccessingSecurityScopedResource() } }
        if stale { UserDefaults.standard.set(try? url.bookmarkData(), forKey: "bookmark") }
        await read(url)
    }

    private func read(_ url: URL) async {
        // iCloud에서 아직 내려받지 않은 파일이면 조정된 읽기가 내려받기를 기다린다(그동안 화면이 멈추지 않게 따로 돌린다)
        let result: Result<Data, Error> = await Task.detached {
            var data: Data?, err: NSError?
            NSFileCoordinator().coordinate(readingItemAt: url, error: &err) { data = try? Data(contentsOf: $0) }
            if let data { return .success(data) }
            return .failure(err ?? CocoaError(.fileReadUnknown))
        }.value
        do {
            let data = try result.get()
            lib = try JSONDecoder().decode(Library.self, from: data)
            try? data.write(to: cache)
            error = nil
        } catch {
            self.error = "서재 파일을 읽지 못했습니다: \(error.localizedDescription)"
        }
    }
}

struct RootView: View {
    @State private var store = Store()
    @State private var picking = false
    @State private var tab = 0

    var body: some View {
        Group {
            if let lib = store.lib {
                TabView(selection: $tab) {
                    Tab("오늘 호", systemImage: "newspaper", value: 0) {
                        NavigationStack { NewsView(lib: lib, tab: $tab).toolbar { menu } }
                    }
                    Tab("논문 서재", systemImage: "books.vertical", value: 1) {
                        NavigationStack { LibraryView(lib: lib).toolbar { menu } }
                    }
                }
                .tint(Ink.ink)
                .refreshable { await store.reload() }
            } else {
                setup
            }
        }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.json]) {
            if case .success(let url) = $0 { Task { await store.pick(url) } }
        }
        .task { await store.reload() }
        .preferredColorScheme(.light)
    }

    private var menu: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Menu {
                Button("다시 읽기", systemImage: "arrow.clockwise") { Task { await store.reload() } }
                Button("다른 파일 고르기", systemImage: "folder") { picking = true }
            } label: { Image(systemName: "ellipsis.circle") }
        }
    }

    private var setup: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("DAILY PAPER").font(mono(12, .medium)).foregroundStyle(Ink.ink2)
            Text("논문 \(Text("신문").foregroundStyle(Ink.red))").font(serif(40, .black))
            Text("Mac 대시보드가 iCloud Drive의 DailyPaper 폴더에 서재 파일(library.json)을 만들어 둡니다. 그 파일을 한 번 고르면 이 앱이 읽어 옵니다.")
                .font(.system(size: 15)).foregroundStyle(Ink.ink2).lineSpacing(4)
            Text("파일이 없으면 Mac에서 대시보드를 켜고 오늘 호나 논문 서재를 한 번 열어 주세요.")
                .font(.system(size: 13)).foregroundStyle(Ink.ink3)
            Button { picking = true } label: {
                Text("iCloud Drive에서 library.json 고르기").font(.system(size: 15, weight: .semibold))
                    .padding(.horizontal, 20).padding(.vertical, 12).background(Ink.ink, in: Capsule()).foregroundStyle(Ink.paper)
            }
            if let e = store.error { Text(e).font(.system(size: 13)).foregroundStyle(Color(hex: 0x7E2E1C)) }
        }
        .padding(24).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading).background(Ink.paper)
    }
}
