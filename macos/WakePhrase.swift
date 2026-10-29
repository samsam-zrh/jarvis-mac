import Foundation

enum WakePhrase {
    static func command(in text: String) -> String? {
        let pattern = #"\b(?:jarvis|jarvice|jervis)\b[\s,.:;!?-]*(.*)"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive, .dotMatchesLineSeparators]),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let range = Range(match.range(at: 1), in: text) else { return nil }
        return String(text[range]).trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

enum TurnBoundary {
    static func shouldSubmit(text: String, silence: Double, acousticComplete: Bool?) -> Bool {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        let unfinished = text.range(of: #"\b(et|puis|ensuite|avec|pour|que|qui|de|du|des|le|la|les|un|une|à|au|aux|dans|sur|si|quand|euh)\s*[,.…:;!?]*$"#,
            options: [.regularExpression, .caseInsensitive]) != nil
        // A confident acoustic ending is fast; a hesitation gets more room.
        if unfinished || acousticComplete == false { return silence >= 3.5 }
        return silence >= (acousticComplete == true ? 1.1 : 1.65)
    }
}
