import SwiftUI

// 오늘 호: 가장 최근 호(또는 고른 지난 호)를 신문 판형으로(대시보드 newsPage()). 머리기사는 요약한 논문 중 첫 편, 다른 기사를 누르면 머리기사로
struct NewsView: View {
    let lib: Library
    @Binding var tab: Int
    @State private var issueNo: Int?
    @State private var sel: String?
    @State private var open: Paper?

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                if let iss = lib.issues.first(where: { $0.no == issueNo }) ?? lib.issues.first {
                    page(iss, proxy).padding(16)
                } else {
                    Text("아직 나온 호가 없습니다. Mac 대시보드에서 \"지금 논문 찾기\"를 하면 첫 호가 나옵니다.")
                        .font(serif(16, .regular)).foregroundStyle(Ink.ink3).padding(40)
                }
            }
        }
        .background(Ink.paper)
        .foregroundStyle(Ink.ink)
        .sheet(item: $open) { BookDetail(p: $0, lib: lib) }
    }

    private func page(_ iss: Library.Issue, _ proxy: ScrollViewProxy) -> some View {
        let today = lib.papers.filter { $0.issue == iss.no }
        let lead = today.first { $0.id == sel } ?? today.first { $0.status != "후보" } ?? today[0]
        let date = today[0].date, day = lib.days[date]
        let n = { (f: (Paper) -> Bool) in today.filter(f).count }
        let summarized = n { $0.status != "후보" }
        let kws = today.map(\.kw).filter { !$0.isEmpty }.reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
        let published = day?.notion == true || (lib.synced ?? "") != "" && today.contains { !$0.notion.isEmpty }
        let steps: [(String, String, String?)] = [
            ("검색", "OpenAlex·Exa 최근 \(lib.period ?? 30)일", day.map { String($0.found) }),
            ("거르기", "이름만 같은 다른 분야 제외", String(today.count)),
            ("PDF·조테로", "오픈 액세스 원문 저장", String(n { $0.zotero })),
            ("요약", "원문 근거와 함께", String(summarized)),
            ("노션 신문", "그날 호 발행", published ? "NO." + nos(iss.no) : nil),
        ]

        return VStack(alignment: .leading, spacing: 0) {
            // 제호
            VStack(alignment: .leading, spacing: 8) {
                Flow(spacing: 14) {
                    Text("NO." + nos(iss.no))
                    if !date.isEmpty { Text(longDate(date)) }
                    Text("OpenAlex · Exa")
                }
                .font(mono(12, .medium)).foregroundStyle(Ink.ink2)
                Text("\(iss == lib.issues.first ? "오늘의 " : "지난 호 · ")\(Text("논문").foregroundStyle(Ink.red)) 신문")
                    .font(serif(38, .black)).tracking(-1)
                Text(lib.schedule.flatMap { $0.isEmpty ? nil : "다음 자동 발행 · 매일 \($0)" } ?? "매일 예약 꺼짐")
                    .font(mono(12)).foregroundStyle(Ink.ink3)
            }
            .padding(.bottom, 12).frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { VStack(spacing: 2) { Ink.ink.frame(height: 1); Ink.ink.frame(height: 1) } }
            .id("top")

            VStack(alignment: .leading, spacing: 4) {
                kws.enumerated().reduce(Text("키워드 ")) { Text("\($0)\($1.offset > 0 ? " · " : "")\(Text($1.element).foregroundStyle(Ink.red).fontWeight(.semibold))") }
                Text("수집 \(today.count) · 요약 \(summarized) · 조테로 \(n { $0.zotero }) · 오픈 액세스 \(n { !$0.oa.isEmpty })")
            }
            .font(.system(size: 13)).foregroundStyle(Ink.ink2).padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { Ink.rule.frame(height: 1) }

            // 그날 실행 단계
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 1) {
                    ForEach(Array(steps.enumerated()), id: \.offset) { i, s in
                        VStack(alignment: .leading, spacing: 0) {
                            Text("0\(i + 1)").font(mono(11, .medium)).foregroundStyle(Ink.ink3)
                            Text(s.0).font(serif(16)).padding(.top, 6)
                            Text(s.1).font(.system(size: 12)).foregroundStyle(Ink.ink2).lineLimit(2).frame(height: 34, alignment: .top).padding(.top, 2)
                            Text(s.2 ?? "—").font(mono(26, .bold)).foregroundStyle(s.2 == nil ? Ink.rule : Ink.ink).padding(.top, 10)
                        }
                        .padding(14).frame(width: 128, alignment: .leading).background(Ink.paper)
                    }
                }
                .background(Ink.rule).overlay(Rectangle().stroke(Ink.ink))
            }
            .padding(.vertical, 24)

            // 머리기사
            header("머리기사", lead.kw)
            VStack(alignment: .leading, spacing: 0) {
                Text(lead.kw.uppercased()).font(mono(12, .semibold)).tracking(0.7).foregroundStyle(lib.kwColor(lead.kw))
                Text(lead.title).font(serif(28)).tracking(-0.5).lineSpacing(5).padding(.top, 8).padding(.bottom, 16)
                if !lead.tldr.isEmpty { Tldr(p: lead, size: 18).padding(.bottom, 14) }
                ByLine(p: lead)
                PaperChips(p: lead).padding(.vertical, 14)
                SummaryTable(p: lead)
                PaperLinks(p: lead).padding(.top, 24)
            }

            // 함께 들어온 논문
            let more = today.filter { $0 != lead }
            if !more.isEmpty {
                VStack(spacing: 0) {
                    ForEach(more) { p in
                        Button {
                            sel = p.id
                            withAnimation { proxy.scrollTo("top", anchor: .top) }
                        } label: {
                            VStack(alignment: .leading, spacing: 0) {
                                HStack(spacing: 8) {
                                    Text(p.kw.uppercased()).font(mono(11, .semibold)).foregroundStyle(lib.kwColor(p.kw)).lineLimit(1)
                                    StatusTag(s: p.status)
                                }
                                Text(p.title).font(serif(18)).lineSpacing(4).padding(.top, 6).padding(.bottom, 8)
                                Text(p.tldr).font(serif(15, .regular)).italic(p.status == "후보").foregroundStyle(p.status == "후보" ? Ink.ink3 : Ink.ink2)
                                    .lineLimit(4).lineSpacing(5).padding(.bottom, 8)
                                Text([p.authorShort, p.venue].filter { !$0.isEmpty }.joined(separator: " · ")).font(.system(size: 13)).foregroundStyle(Ink.ink2)
                            }
                            .multilineTextAlignment(.leading).frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 18)
                            .overlay(alignment: .bottom) { Ink.rule.frame(height: 1) }
                        }
                        .buttonStyle(.plain)
                    }
                }
                .overlay(alignment: .top) { Ink.ink.frame(height: 1) }
                .padding(.top, 30)
            }

            // 지난 호
            header("지난 호", "\(lib.issues.count)호").padding(.top, 34)
            VStack(spacing: 0) {
                ForEach(lib.issues, id: \.self) { i in
                    Button {
                        issueNo = i.no
                        sel = nil
                        withAnimation { proxy.scrollTo("top", anchor: .top) }
                    } label: {
                        HStack {
                            Text("NO." + nos(i.no)).font(mono(14, .bold))
                            Spacer()
                            Text("\(i.date) · \(lib.papers.filter { $0.issue == i.no }.count)편").font(mono(12)).foregroundStyle(Ink.ink3)
                        }
                        .padding(.vertical, 10).padding(.horizontal, 2).background(i == iss ? Ink.paper2 : .clear)
                        .overlay(alignment: .bottom) { Ink.rule.frame(height: 1) }
                    }
                    .buttonStyle(.plain)
                }
            }

            // 최근 서가
            HStack(alignment: .firstTextBaseline) {
                Text("최근 서가").font(mono(13, .bold)).tracking(1)
                Spacer()
                Button("전체 보기") { tab = 1 }.font(mono(12)).foregroundStyle(Ink.ink3).underline()
            }
            .padding(.bottom, 6).overlay(alignment: .bottom) { Ink.ink.frame(height: 1) }.padding(.top, 34).padding(.bottom, 16)
            let shelf = lib.papers.sorted { $0.issue > $1.issue }.prefix(10)
            VStack(spacing: 0) {
                HStack(alignment: .bottom, spacing: 3) {
                    ForEach(Array(shelf.enumerated()), id: \.element.id) { i, p in
                        Spine(p: p, c: lib.pal(p), height: CGFloat(110 + i * 37 % 40), width: 26, size: 10, year: false)
                            .opens(p, $open)
                    }
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 10).padding(.top, 14).background(Ink.wood).clipped()
                Rectangle().fill(Ink.board).frame(height: 10)
            }
            .clipShape(RoundedRectangle(cornerRadius: 4))
        }
    }

    private func header(_ title: String, _ right: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(mono(13, .bold)).tracking(1)
            Spacer()
            Text(right).font(mono(12)).foregroundStyle(Ink.ink3).lineLimit(1)
        }
        .padding(.bottom, 6).overlay(alignment: .bottom) { Ink.ink.frame(height: 1) }.padding(.bottom, 16)
    }
}

private func longDate(_ d: String) -> String {
    let f = DateFormatter()
    f.locale = Locale(identifier: "ko_KR")
    f.dateFormat = "yyyy-MM-dd"
    guard let x = f.date(from: d) else { return d }
    f.dateFormat = "yyyy년 M월 d일 EEEE"
    return f.string(from: x)
}
