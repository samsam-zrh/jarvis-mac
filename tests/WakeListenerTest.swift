import Foundation

@main struct WakeListenerTest {
    static func main() {
        let wake = WakeListener()
        var interruptions = 0
        var commands: [String] = []
        wake.onInterrupt = { interruptions += 1 }
        wake.onCommand = { commands.append($0) }
        wake.suspend(true)
        wake.receive("Jarvis")
        wake.receive("ouvre Pages")
        RunLoop.main.run(until: Date().addingTimeInterval(2))
        precondition(interruptions == 1, "Jarvis must interrupt speech exactly once")
        precondition(commands == ["ouvre Pages"], "The command after the interruption must not be dropped")

        let repeated = WakeListener()
        var repeatedCommands: [String] = []
        repeated.onCommand = { repeatedCommands.append($0) }
        repeated.receive("Jarvis ouvre Spotify")
        for delay in [0.2, 0.4, 0.6] {
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { repeated.receive("Jarvis ouvre Spotify") }
        }
        RunLoop.main.run(until: Date().addingTimeInterval(2))
        precondition(repeatedCommands == ["ouvre Spotify"], "Duplicate partials must not postpone submission")
        precondition(!TurnBoundary.shouldSubmit(text:"ouvre Spotify et",silence:1.8,acousticComplete:true))
        precondition(!TurnBoundary.shouldSubmit(text:"écris un message",silence:1.8,acousticComplete:false))
        precondition(TurnBoundary.shouldSubmit(text:"ouvre Spotify",silence:1.2,acousticComplete:true))
        let long = WakeListener()
        var longCommands: [String] = []
        long.onCommand = { longCommands.append($0) }
        long.receive("Jarvis écris un message à Emma et")
        DispatchQueue.main.asyncAfter(deadline: .now()+1.7) {
            precondition(longCommands.isEmpty, "A mid-sentence pause must not submit the first half")
            long.receive("Jarvis écris un message à Emma et dis-lui que j’arrive à dix-huit heures puis ouvre mes mails")
        }
        RunLoop.main.run(until: Date().addingTimeInterval(3.7))
        precondition(longCommands.count == 1 && longCommands[0].contains("ouvre mes mails"))
        print("6 voice state and turn-boundary regression tests passed")
    }
}
