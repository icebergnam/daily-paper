import SwiftUI

// 대시보드 .lib의 종이·나무 책장 디자인(scripts/대시보드.py의 CSS와 PAL·hashN)을 옮긴 것
extension Color {
    init(hex: UInt32) {
        self.init(red: Double(hex >> 16 & 0xff) / 255, green: Double(hex >> 8 & 0xff) / 255, blue: Double(hex & 0xff) / 255)
    }
}

enum Ink {
    static let paper = Color(hex: 0xF5F1E8), paper2 = Color(hex: 0xEDE7DA), ink = Color(hex: 0x1F1B16), ink2 = Color(hex: 0x5B544A)
    static let ink3 = Color(hex: 0x8F877B), rule = Color(hex: 0xD9D1C1), red = Color(hex: 0xB4472F), green = Color(hex: 0x2F5D50), blue = Color(hex: 0x2C4A7A)
    static let wood = Color(hex: 0x3A2A1D), board = LinearGradient(colors: [Color(hex: 0xA8784A), Color(hex: 0x7C5530)], startPoint: .top, endPoint: .bottom)
}

private let hasSerif = UIFont.familyNames.contains("Noto Serif KR")
func serif(_ size: CGFloat, _ w: Font.Weight = .bold) -> Font {
    hasSerif ? .custom("Noto Serif KR", size: size).weight(w) : .system(size: size, weight: w, design: .serif)
}
func mono(_ size: CGFloat, _ w: Font.Weight = .regular) -> Font { .system(size: size, weight: w, design: .monospaced) }
func nos(_ n: Int) -> String { String(format: "%03d", n) }

func hashN(_ s: String, _ m: Int) -> Int {
    var h: UInt32 = 0
    for u in s.unicodeScalars { h = h &* 31 &+ u.value }
    return Int(h % UInt32(m))
}

struct BookColor { let bg, fg, band: Color }
private func bc(_ bg: UInt32, _ fg: UInt32, _ band: UInt32) -> BookColor { BookColor(bg: Color(hex: bg), fg: Color(hex: fg), band: Color(hex: band)) }
// 키워드 순서대로 노션 키워드 색(red → green → blue → orange → purple → pink → brown)에 맞춘 책 색
private let PAL: [[BookColor]] = [
    [bc(0xB4472F, 0xFBEFE4, 0x1F1B16), bc(0xE9DCC6, 0x7E2E1C, 0xB4472F), bc(0x5A2318, 0xF2D9C2, 0xE08A5E), bc(0xD9714F, 0x2A130C, 0xFBEFE4)],
    [bc(0x2F5D50, 0xEEF2E6, 0xD9B65A), bc(0xDCE5D6, 0x21433A, 0x2F5D50), bc(0x1C3830, 0xD9E4CF, 0x8FB59E)],
    [bc(0x2C4A7A, 0xEEF0F5, 0xE2B04A), bc(0xE3E6EE, 0x1E3358, 0x2C4A7A), bc(0x16233C, 0xD7DEEC, 0x6F8FC4)],
    [bc(0xC77B2E, 0xFFF4E6, 0x3A2410), bc(0xF1DFC4, 0x6E3F12, 0xC77B2E)],
    [bc(0x6B4C8A, 0xF2ECF7, 0xD9B65A), bc(0xE5DDEE, 0x4A2F66, 0x6B4C8A)],
    [bc(0xB5536F, 0xFBEEF2, 0x3B1622), bc(0xF1DCE2, 0x7A2C43, 0xB5536F)],
    [bc(0x7A5A3A, 0xF5ECE0, 0xD9B65A), bc(0xE6DACB, 0x4E3720, 0x7A5A3A)],
]

extension Library {
    func pal(_ p: Paper) -> BookColor {
        let l = PAL[max(0, keywords.firstIndex(of: p.kw) ?? 0) % PAL.count]
        return l[hashN(p.id, l.count)]
    }
    func kwColor(_ k: String) -> Color { PAL[(keywords.firstIndex(of: k) ?? 0) % PAL.count][0].bg }
}

// 수치(β·R²·p·AUC·%)에 형광펜
func hl(_ s: String) -> AttributedString {
    var a = AttributedString(s)
    for m in s.matches(of: #/β\s?=\s?−?[\d.]+|R²\s?=\s?[\d.]+|p\s?[<=]\s?[\d.]+|AUC\s?[\d.]+|\d[\d.]*%/#) {
        if let r = Range(m.range, in: a) { a[r].backgroundColor = Color(hex: 0xFBE3D7) }
    }
    return a
}

struct BookCover: View {
    let p: Paper, c: BookColor
    var width: CGFloat = 132

    var body: some View {
        let s = width / 132, h = width * 1.42
        VStack(alignment: .leading, spacing: 0) {
            Text(p.kw.uppercased()).font(mono(8 * s, .bold)).tracking(1).lineLimit(1).opacity(0.85)
            Rectangle().frame(height: 1).opacity(0.35).padding(.top, 7 * s)
            Text(p.short).font(serif(15 * s)).lineLimit(5).padding(.top, 8 * s)
            Spacer(minLength: 0)
            Text(p.authorShort).font(.system(size: 9 * s, weight: .medium)).lineLimit(1).opacity(0.85)
            HStack {
                Text("NO." + nos(p.issue))
                Spacer()
                Text(p.year.map(String.init) ?? "")
            }
            .font(mono(9 * s, .bold)).opacity(0.7).padding(.top, 3 * s)
        }
        .padding(EdgeInsets(top: 15 * s, leading: 18 * s, bottom: 13 * s, trailing: 13 * s))
        .frame(width: width, height: h, alignment: .topLeading)
        .foregroundStyle(c.fg)
        .background(alignment: .bottom) {
            ZStack(alignment: .bottom) {
                c.bg
                c.band.frame(height: h * 0.05).opacity(0.9).padding(.bottom, h * 0.22)
            }
        }
        .overlay(alignment: .leading) {
            LinearGradient(colors: [.black.opacity(0.28), .white.opacity(0.08), .black.opacity(0.08)], startPoint: .leading, endPoint: .trailing)
                .frame(width: width * 0.07)
        }
        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 2, bottomLeadingRadius: 2, bottomTrailingRadius: 4, topTrailingRadius: 4))
        .shadow(color: Color(hex: 0x28190A).opacity(0.35), radius: 7, x: 6, y: 8)
    }
}

struct Spine: View {
    let p: Paper, c: BookColor, height: CGFloat
    var width: CGFloat = 34, size: CGFloat = 12, year = true

    var body: some View {
        let len = height - 18 - (year ? 16 : 0)
        VStack(spacing: 6) {
            Text(p.short).font(serif(size)).lineLimit(1).frame(width: len).rotationEffect(.degrees(90)).frame(width: width, height: len)
            if year { Text(p.year.map { String($0 % 100) } ?? "").font(mono(8, .bold)).opacity(0.75) }
        }
        .padding(.top, 10).padding(.bottom, 8)
        .frame(width: width, height: height, alignment: .top)
        .foregroundStyle(c.fg)
        .background {
            ZStack {
                c.bg
                VStack {
                    c.band.frame(height: 3).opacity(0.6).padding(.top, 18)
                    Spacer()
                    c.band.frame(height: 3).opacity(0.6).padding(.bottom, 30)
                }
                LinearGradient(colors: [.white.opacity(0.15), .clear, .black.opacity(0.2)], startPoint: .leading, endPoint: .trailing)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 2))
    }
}

struct StatusTag: View {
    let s: String
    var body: some View {
        let (bg, fg) = s == "요약 완료" ? (Color(hex: 0xE2ECE6), Ink.green) : s == "읽는 중" ? (Color(hex: 0xE1E7F1), Ink.blue) : (Color(hex: 0xF6E6C8), Color(hex: 0x8A5A12))
        Text(s).font(mono(11, .semibold)).padding(.horizontal, 7).padding(.vertical, 2)
            .background(bg, in: RoundedRectangle(cornerRadius: 3)).foregroundStyle(fg).fixedSize()
    }
}

// 줄이 넘치면 다음 줄로(칩·링크)
struct Flow: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        rows(proposal.width ?? .infinity, subviews).size
    }

    func placeSubviews(in b: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for (i, pt) in rows(b.width, subviews).points.enumerated() {
            subviews[i].place(at: CGPoint(x: b.minX + pt.x, y: b.minY + pt.y), proposal: ProposedViewSize(width: b.width, height: nil))
        }
    }

    private func rows(_ w: CGFloat, _ subs: Subviews) -> (points: [CGPoint], size: CGSize) {
        var pts: [CGPoint] = [], x: CGFloat = 0, y: CGFloat = 0, rowH: CGFloat = 0, maxX: CGFloat = 0
        for s in subs {
            let sz = s.sizeThatFits(ProposedViewSize(width: w, height: nil))
            if x > 0 && x + sz.width > w { x = 0; y += rowH + spacing; rowH = 0 }
            pts.append(CGPoint(x: x, y: y))
            x += sz.width + spacing
            rowH = max(rowH, sz.height)
            maxX = max(maxX, x - spacing)
        }
        return (pts, CGSize(width: maxX, height: y + rowH))
    }
}

struct Chip: View {
    let text: String
    var fg = Ink.ink2, bg = Ink.paper2, border = Ink.rule
    var body: some View {
        Text(text).font(mono(12, .medium)).padding(.horizontal, 9).padding(.vertical, 4).foregroundStyle(fg)
            .background(bg, in: RoundedRectangle(cornerRadius: 4)).overlay(RoundedRectangle(cornerRadius: 4).stroke(border))
    }
}

struct PaperChips: View {
    let p: Paper
    var body: some View {
        Flow {
            StatusTag(s: p.status)
            if p.zotero { Chip(text: "✓ 조테로 저장", fg: Ink.green, bg: Color(hex: 0xE8EFE9), border: Color(hex: 0xBCD0C6)) }
            if !p.oa.isEmpty { Chip(text: "오픈 액세스") }
            ForEach(p.ev, id: \.self) { Chip(text: "근거 " + $0, fg: Ink.red, bg: .white, border: Color(hex: 0xE6C9BF)) }
        }
    }
}

struct ByLine: View {
    let p: Paper
    var body: some View {
        Text("\(Text(p.authors).fontWeight(.semibold).foregroundStyle(Ink.ink)) — \(p.year.map(String.init) ?? "") · \(p.venue)")
            .font(.system(size: 13)).foregroundStyle(Ink.ink2).lineSpacing(3)
    }
}

struct Tldr: View {
    let p: Paper
    var size: CGFloat = 17
    var body: some View {
        let cand = p.status == "후보"
        Text(hl(p.tldr)).font(serif(size, .regular)).italic(cand).foregroundStyle(cand ? Ink.ink3 : Ink.ink).lineSpacing(size * 0.5)
            .padding(.leading, 16).overlay(alignment: .leading) { Rectangle().fill(cand ? Color(hex: 0xD9B65A) : Ink.ink).frame(width: 3) }
    }
}

struct SummaryTable: View {
    let p: Paper
    var body: some View {
        VStack(spacing: 0) {
            ForEach(p.table, id: \.self) { row in
                HStack(alignment: .top, spacing: 0) {
                    Text(row.first ?? "").font(serif(13)).foregroundStyle(Ink.ink2).frame(width: 56, alignment: .leading)
                    Text(hl(row.last ?? "")).font(.system(size: 14)).lineSpacing(5).frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.vertical, 11).overlay(alignment: .top) { Ink.rule.frame(height: 1) }
            }
        }
    }
}

struct PaperLinks: View {
    let p: Paper
    var body: some View {
        Flow(spacing: 8) {
            if let u = URL(string: p.notion), !p.notion.isEmpty {
                Link(destination: u) {
                    HStack(spacing: 10) {
                        Text("N").font(serif(14)).frame(width: 26, height: 26).overlay(RoundedRectangle(cornerRadius: 5).stroke(lineWidth: 1.5))
                        Text("노션 페이지 열기").fontWeight(.semibold)
                    }
                    .linkBox(Ink.ink)
                }
            }
            if let u = URL(string: p.oa), !p.oa.isEmpty { Link(destination: u) { Text("원문 PDF").linkBox(Ink.rule) } }
            if let u = URL(string: p.url), !p.url.isEmpty { Link(destination: u) { Text("DOI · 출처").linkBox(Ink.rule) } }
        }
        .font(.system(size: 14)).foregroundStyle(Ink.ink)
    }
}

private extension View {
    func linkBox(_ border: Color) -> some View {
        padding(.horizontal, 16).padding(.vertical, 12).background(.white, in: RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(border))
    }
}

// 책을 누르면 열리는 요약 서랍
struct BookDetail: View {
    let p: Paper, lib: Library

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                BookCover(p: p, c: lib.pal(p), width: 150)
                    .frame(maxWidth: .infinity).frame(height: 260).background(Ink.paper2, in: RoundedRectangle(cornerRadius: 6))
                Text("\(p.kw.uppercased()) · NO.\(nos(p.issue))").font(mono(12, .semibold)).tracking(0.7)
                    .foregroundStyle(lib.kwColor(p.kw)).padding(.top, 20)
                Text(p.title).font(serif(24)).lineSpacing(6).padding(.top, 8).padding(.bottom, 10)
                ByLine(p: p)
                PaperChips(p: p).padding(.vertical, 14)
                if !p.tldr.isEmpty { Tldr(p: p).padding(.bottom, 14) }
                SummaryTable(p: p)
                PaperLinks(p: p).padding(.top, 24)
                if p.notion.isEmpty {
                    Text("노션 페이지 주소는 대시보드의 \"노션과 동기화\" 뒤에 생깁니다.").font(.system(size: 13)).foregroundStyle(Ink.ink3).padding(.top, 10)
                }
            }
            .foregroundStyle(Ink.ink).padding(.horizontal, 20).padding(.vertical, 28)
        }
        .background(Ink.paper)
        .presentationDragIndicator(.visible)
    }
}

extension View {
    // 책 하나를 누를 수 있게: 누르면 요약 서랍
    func opens(_ p: Paper, _ open: Binding<Paper?>) -> some View {
        Button { open.wrappedValue = p } label: { self }.buttonStyle(.plain).accessibilityLabel(p.title)
    }
}
