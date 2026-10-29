import Foundation

@main struct WakePhraseTest {
    static func main() {
        precondition(WakePhrase.command(in: "Jarvis ouvre mon document") == "ouvre mon document")
        precondition(WakePhrase.command(in: "Hé Jarvis, quelle heure est-il ?") == "quelle heure est-il ?")
        precondition(WakePhrase.command(in: "JARVIS") == "")
        precondition(WakePhrase.command(in: "jervis crée un document") == "crée un document")
        precondition(WakePhrase.command(in: "Un logiciel jarvisien") == nil)
        precondition(WakePhrase.command(in: "Bonjour, ouvre mon document") == nil)
        print("6 tests d’activation vocale réussis")
    }
}
