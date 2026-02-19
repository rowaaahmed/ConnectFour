# ConnectFour
Connect Four is a two-player, deterministic, zero-sum strategy game in which players take turns 
dropping colored discs into a vertical grid. Each disc falls straight down to occupy the lowest 
available space within a column. The objective of the game is to be the first player to form a line 
of four consecutive pieces of the same color. These four connected pieces can be arranged 
horizontally, vertically, or diagonally across the board. 

Because the game has perfect information, both players can fully observe the state of the board at 
all times meaning that winning relies entirely on strategic planning rather than chance. The game 
ends when one player successfully creates a sequence of four pieces, or when the board becomes 
completely filled, resulting in a draw. 

However, for the purposes of this application, we make an additional simplifying assumption: the 
game does not end immediately when a player forms four connected pieces. Instead, play continues 
until the entire board is completely filled. Once the board is full, the winner is determined by 
comparing the total number of distinct four-in-a-row connections achieved by each player 
throughout the game. The player with the greater number of valid connected fours is declared the 
winner. This modified rule allows the game to be treated more like a scoring-based system rather 
than a sudden-win condition.

# Algorithms Used for gameplaying
1. Minimax Algorithm

2. Minimax with Alpha–Beta Pruning

3. Expectiminimax Algorithm

# GUI

<img width="885" height="455" alt="image" src="https://github.com/user-attachments/assets/241e86f3-d3ff-419c-bb73-a4df720f411f" />


<img width="885" height="490" alt="image" src="https://github.com/user-attachments/assets/f76c7619-29f2-45d6-97b6-5323b188fef8" />


<img width="886" height="383" alt="image" src="https://github.com/user-attachments/assets/0cb78c43-1ade-484e-b549-d5b3a5dc3317" />


<img width="975" height="530" alt="image" src="https://github.com/user-attachments/assets/7b2b9549-5115-4252-a700-f2c0efb19709" />


## Search Algorithm Performance Comparison

| Depth | MiniMax Nodes | MiniMax Time (s) | Pruning Nodes | Pruning Time (s) | Expecti Nodes | Expecti Time (s) |
|-------|--------------|------------------|---------------|------------------|---------------|------------------|
| 1     | 8            | 0.001            | 8             | 0.001            | null          | null             |
| 2     | 57           | 0.003            | 21            | 0.007            | 27            | 0.000            |
| 3     | 295          | 0.017            | 61            | 0.018            | null          | null             |
| 4     | 1415         | 0.081            | 134           | 0.049            | 209           | 0.023            |
| 5     | 5678         | 0.337            | 509           | 0.160            | null          | null             |
| 6     | 22100        | 1.361            | 622           | 0.248            | 1483          | 0.023            |
| 7     | 76959        | 4.961            | 2224          | 0.734            | null          | null             |
| 8     | 263348       | 17.390           | 6415          | 2.474            | 7671          | 8.677            |
| 9     | 830789       | 57.573           | 18816         | 6.724            | null          | null             |
| 10    | 5777689      | 165.951          | 20274         | 7.946            | 36791         | 0.550            |






