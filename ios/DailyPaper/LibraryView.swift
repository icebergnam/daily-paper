import SwiftUI

// 논문 서재: 노션 아카이브를 책장으로(대시보드 libPage()). 신간 매대·키워드별·읽기 상태별·호별, 책장·표지 보기
struct LibraryView: View {
    let lib: Library
    @AppStorage("lib_group") private var group = "kw"
    @AppStorage("lib_mode") private var mode = "case"
    @State private var q = ""
    @State private var open: Paper?

    private struct Shelf: Identifiable { let id, label: String; let color: Color; let items: [Paper] }

    var body: some View {
        let papers = lib.papers.filter { q.isEmpty || [$0.title, $0.authors, $0.venue, $0.tldr].joined(separator: " ").localizedCaseInsensitiveContains(q) }
        let top = lib.papers.map(\.issue).max() ?? 0
        let shelves: [Shelf] = switch group {
        case "new": [Shelf(id: "new", label: "NO.\(nos(top)) 신간", color: Ink.red, items: papers.filter(\.isNew))]
        case "status": [("후보", Color(hex: 0x8A5A12)), ("읽는 중", Ink.blue), ("요약 완료", Ink.green)].map { s, c in
            Shelf(id: s, label: s, color: c, items: papers.filter { $0.status == s }) }
        case "issue": lib.issues.map { i in Shelf(id: "i\(i.no)", label: "NO.\(nos(i.no)) · \(i.date)", color: Ink.ink, items: papers.filter { $0.issue == i.no }) }
        default: lib.keywords.map { k in Shelf(id: k, label: k, color: lib.kwColor(k), items: papers.filter { $0.kw == k }) }
        }
        let reading = papers.filter { $0.status == "읽는 중" }

        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 14) { Text("LIBRARY"); Text("노션 · 논문 아카이브"); Text("\(lib.papers.count)권") }
                        .font(mono(12, .medium)).foregroundStyle(Ink.ink2)
                    Text("논문 \(Text("서재").foregroundStyle(Ink.red))").font(serif(30, .black)).tracking(-1)
                    Text(lib.synced.flatMap { $0.isEmpty ? nil : "마지막 동기화 · \($0)" } ?? "아직 동기화하지 않음 · 로컬 기록으로 보는 중")
                        .font(mono(12)).foregroundStyle(Ink.ink3)
                }
                .padding(.bottom, 12).frame(maxWidth: .infinity, alignment: .leading)
                .overlay(alignment: .bottom) { VStack(spacing: 2) { Ink.ink.frame(height: 1); Ink.ink.frame(height: 1) } }

                VStack(spacing: 10) {
                    Picker("묶기", selection: $group) {
                        Text("신간 매대").tag("new"); Text("키워드별").tag("kw"); Text("읽기 상태별").tag("status"); Text("호별").tag("issue")
                    }
                    Picker("보기", selection: $mode) { Text("책장").tag("case"); Text("표지").tag("grid") }
                }
                .pickerStyle(.segmented).padding(.vertical, 16)

                if group == "kw" && !reading.isEmpty { desk(reading) }

                if lib.papers.isEmpty {
                    none("아직 서재에 논문이 없습니다. Mac 대시보드에서 \"지금 논문 찾기\"를 하면 꽂힙니다.")
                } else if !q.isEmpty && papers.isEmpty {
                    none("“\(q)”에 맞는 논문이 서재에 없습니다.")
                } else if mode == "case" {
                    bookcase(shelves)
                } else {
                    covers(shelves.filter { !$0.items.isEmpty })
                }
            }
            .padding(16)
        }
        .searchable(text: $q, prompt: "제목 · 저자 · 저널 · 요약에서 찾기")
        .background(Ink.paper)
        .foregroundStyle(Ink.ink)
        .sheet(item: $open) { BookDetail(p: $0, lib: lib) }
    }

    private func none(_ s: String) -> some View {
        Text(s).font(serif(16, .regular)).foregroundStyle(Ink.ink3).multilineTextAlignment(.center).frame(maxWidth: .infinity).padding(.vertical, 40)
    }

    // 책상 위: 읽는 중인 책을 눕혀 쌓는다
    private func desk(_ reading: [Paper]) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(Text("책상 위").font(serif(18)).foregroundStyle(Ink.ink))\n읽는 중 \(reading.count)권").font(.system(size: 13)).foregroundStyle(Ink.ink2)
                .padding(.bottom, 6)
            ForEach(Array(reading.enumerated().reversed()), id: \.element.id) { i, p in
                let c = lib.pal(p)
                HStack(spacing: 12) {
                    Text(p.short).font(serif(12.5)).lineLimit(1).padding(.leading, 16)
                    Spacer(minLength: 0)
                    Text(p.authorShort).font(mono(10, .medium)).opacity(0.75).lineLimit(1)
                }
                .padding(.horizontal, 14).frame(height: 30).foregroundStyle(c.fg)
                .background(alignment: .leading) { ZStack(alignment: .leading) { c.bg; c.band.frame(width: 3).opacity(0.7).padding(.leading, 22) } }
                .clipShape(RoundedRectangle(cornerRadius: 3))
                .shadow(color: Color(hex: 0x28190A).opacity(0.2), radius: 2, x: 2, y: 2)
                .padding(.leading, CGFloat(i * 14)).padding(.trailing, CGFloat(i * 4))
                .opens(p, $open)
            }
            LinearGradient(colors: [Color(hex: 0xC9A77C), Color(hex: 0xA9855A)], startPoint: .top, endPoint: .bottom)
                .frame(height: 12).clipShape(RoundedRectangle(cornerRadius: 3)).shadow(color: Color(hex: 0x3C2814).opacity(0.2), radius: 5, y: 6)
        }
        .padding(.bottom, 30)
    }

    private func bookcase(_ shelves: [Shelf]) -> some View {
        VStack(alignment: .leading, spacing: 22) {
            ForEach(shelves) { g in
                let face = group == "new" ? g.items : Array(g.items.filter(\.isNew).prefix(2))
                let spines = g.items.filter { !face.contains($0) }
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 8) {
                        RoundedRectangle(cornerRadius: 2).fill(g.color).frame(width: 8, height: 8)
                        Text(g.label.uppercased()).lineLimit(1)
                        Text("\(g.items.count)").fontWeight(.medium).foregroundStyle(Color(hex: 0xB9A07A))
                    }
                    .font(mono(11, .bold)).tracking(0.9).foregroundStyle(Color(hex: 0xE7D2AE))
                    .padding(.horizontal, 10).padding(.vertical, 4).background(.black.opacity(0.25), in: RoundedRectangle(cornerRadius: 3))
                    .padding(.bottom, 10)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(alignment: .bottom, spacing: 3) {
                            if g.items.isEmpty {
                                Text("아직 꽂힌 논문이 없습니다").font(serif(13, .regular)).italic().foregroundStyle(Color(hex: 0x8D7558))
                                    .frame(maxHeight: .infinity).padding(.horizontal, 10)
                            }
                            ForEach(face) { p in
                                BookCover(p: p, c: lib.pal(p)).overlay(alignment: .topTrailing) { newBadge }
                                    .padding(.trailing, 12).opens(p, $open)
                            }
                            ForEach(spines) { p in
                                Spine(p: p, c: lib.pal(p), height: CGFloat(168 + hashN(p.id, 34))).opens(p, $open)
                            }
                            if !g.items.isEmpty {
                                ForEach(0..<max(0, 6 - g.items.count), id: \.self) { i in
                                    LinearGradient(colors: [Color(hex: 0x4A3828), Color(hex: 0x56412E)], startPoint: .leading, endPoint: .trailing)
                                        .frame(width: 28, height: CGFloat(150 + hashN(g.id + String(i), 30))).clipShape(RoundedRectangle(cornerRadius: 2)).opacity(0.75)
                                }
                                Color(hex: 0x8A6A45).frame(width: 10, height: 120).clipShape(UnevenRoundedRectangle(topLeadingRadius: 2, topTrailingRadius: 2)).padding(.leading, 6)
                            }
                        }
                        .padding(.horizontal, 10).padding(.top, 14).frame(minHeight: 220, alignment: .bottom)
                    }
                    .background(LinearGradient(colors: [Color(hex: 0x22180F), Color(hex: 0x35261A)], startPoint: .top, endPoint: .bottom))
                    Rectangle().fill(Ink.board).frame(height: 16).shadow(color: .black.opacity(0.45), radius: 5, y: 6)
                }
            }
        }
        .padding(.horizontal, 12).padding(.top, 18).padding(.bottom, 4)
        .background(Ink.wood, in: RoundedRectangle(cornerRadius: 6))
        .padding(8).background(Color(hex: 0x5A3F28), in: RoundedRectangle(cornerRadius: 10))
    }

    private var newBadge: some View {
        Text("NEW").font(mono(10, .bold)).tracking(0.5).foregroundStyle(.white).padding(.horizontal, 6).padding(.vertical, 3)
            .background(Ink.red, in: RoundedRectangle(cornerRadius: 2)).shadow(color: .black.opacity(0.3), radius: 2, y: 2).offset(x: 6, y: -8)
    }

    private func covers(_ shelves: [Shelf]) -> some View {
        VStack(alignment: .leading, spacing: 34) {
            ForEach(shelves) { g in
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(g.label.uppercased()).font(mono(13, .bold)).tracking(1).foregroundStyle(g.color)
                        Spacer()
                        Text("\(g.items.count)권").font(mono(12)).foregroundStyle(Ink.ink3)
                    }
                    .padding(.bottom, 6).overlay(alignment: .bottom) { Ink.rule.frame(height: 1) }
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 22, alignment: .top)], spacing: 26) {
                        ForEach(g.items) { p in
                            VStack(alignment: .leading, spacing: 0) {
                                BookCover(p: p, c: lib.pal(p), width: 96)
                                    .overlay(alignment: .topTrailing) { if p.isNew { newBadge } }
                                    .frame(maxWidth: .infinity).aspectRatio(1 / 1.15, contentMode: .fill)
                                    .background(Ink.paper2, in: RoundedRectangle(cornerRadius: 4))
                                Text(p.title).font(serif(14)).lineLimit(2).lineSpacing(3).padding(.top, 10)
                                Flow {
                                    Text("\(p.authorShort) · NO.\(nos(p.issue))").font(mono(12)).foregroundStyle(Ink.ink3)
                                    StatusTag(s: p.status)
                                }
                                .padding(.top, 5)
                            }
                            .contentShape(Rectangle()).opens(p, $open)
                        }
                    }
                }
            }
        }
    }
}
