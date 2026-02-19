import pygame
import sys
import math
import random
import time

# ==============================
# COLORS & CONSTANTS
# ==============================
BLUE = (40, 90, 200)
BLACK = (0, 0, 0)
RED = (240, 80, 80)
YELLOW = (252, 216, 84)
WHITE = (255, 255, 255)
GRAY = (120, 120, 120)
GREEN = (74, 195, 139)
PANEL_BG = (18, 18, 18)
PANEL_BORDER = (60, 60, 60)
MUTED = (180, 180, 180)

PLAYER = 0
AI = 1
PLAYER_PIECE = 1
AI_PIECE = 2

_search_cache = {}       # to store repeated nodes in
expanded_nodes_count = 0   # to count the number of expanded nodes

pygame.init()
pygame.font.init()

# ==============================
# TUNABLE UI
# ==============================
UI = {
    # --- window & layout ---
    "SCREEN_WIDTH": 1600,
    "SCREEN_HEIGHT": 900,
    "LEFT_RATIO": 0.56,
    "OUTER_MARGIN": 40,
    "BOARD_TOP_PAD": 90,
    "BOARD_BOTTOM_PAD": 50,
    "PANEL_SIDE_PAD": 20,
    "PANEL_INNER_PAD": 18,

    # --- text sizes ---
    "FONT_MAIN": 30,
    "FONT_SMALL": 18,
    "FONT_TREE": 16,

    # --- icons & turn pill ---
    "ICON_SIZE": 44,
    "ICON_GAP": 10,
    "ICON_PAD": 12,
    "TURN_PILL_W": 250,
    "TURN_PILL_H": 56,
    "TURN_PILL_TOP": 74,

    # --- search tree box inside right panel ---
    "TREE_TOP_GAP": 260,
    "TREE_BOTTOM_GAP": 50,
    "TREE_BORDER_RADIUS": 10,

    # --- tidy-tree spacing ---
    "TREE_X_SPACING": 180,
    "TREE_Y_SPACING": 110,
    # draw up to this many levels of the tree
    "TREE_MAX_LEVEL": 15,

    # --- zoom & pan behavior ---
    "ZOOM_STEP": 0.1,
    "ZOOM_MIN": 0.05,
    "ZOOM_MAX": 3.0,
    "PAN_STEP": 60,

    # --- misc ---
    "HOVER_DISC_RATIO": 1/3,
}

# Consistent world padding around root
TREE_LEFT_PAD = 80
TREE_TOP_PAD = 40

# ==============================
# BITBOARD
# ==============================
# This creates the representation that will be used for calculations for the game board 
class BitBoard:
    def __init__(self, rows=6, cols=7):
        self.rows = rows
        self.cols = cols
        self.board_p1 = 0
        self.board_p2 = 0

    # Creates a copy for the board 
    def copy(self):
        b = BitBoard(self.rows, self.cols)
        b.board_p1 = self.board_p1
        b.board_p2 = self.board_p2
        return b

    # Changes the bitboard to an array for GUI
    def get_board_array(self):
        board = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        for c in range(self.cols):
            for r in range(self.rows):
                mask = 1 << (c * (self.rows + 1) + r)
                if self.board_p1 & mask:
                    board[r][c] = PLAYER_PIECE
                elif self.board_p2 & mask:
                    board[r][c] = AI_PIECE
        return board

    # Checks if a column is full or not
    def is_valid_location(self, col):
        top_mask = 1 << (col * (self.rows + 1) + (self.rows - 1))
        return not ((self.board_p1 | self.board_p2) & top_mask)

    # Returns a list of the non-full columns 
    def get_valid_locations(self):
        return [c for c in range(self.cols) if self.is_valid_location(c)]

    def drop_piece(self, col, piece):
        mask = 1 << (col * (self.rows + 1))         # Start at the lowest empty cell
        # while the current bit is occupied and we haven’t reached the top
        while (self.board_p1 | self.board_p2) & mask and (mask < (1 << ((col + 1) * (self.rows + 1) - 1))):
            mask <<= 1              # Move the cell one row up
        top_mask = 1 << (col * (self.rows + 1) + self.rows)
        if (self.board_p1 | self.board_p2) & top_mask:
            return False                      # If col is full, the player can's drop in this col
        if piece == PLAYER_PIECE:
            self.board_p1 |= mask
        else:
            self.board_p2 |= mask
        return True

    # Checks if the whole board is full to reprent the end of the game
    def is_full(self):
        return all(not self.is_valid_location(c) for c in range(self.cols))

# ==============================
# SCORING & HEURISTICS
# ==============================

WINDOW_MASKS = None
CENTER_MASK = None
COLUMN_MASKS = None

# precomputes all 4-cell sequences (windows) for scoring
def precompute_window_masks(rows, cols):
    global WINDOW_MASKS, CENTER_MASK, COLUMN_MASKS
    WINDOW_MASKS = []
    COLUMN_MASKS = [0] * cols

    for c in range(cols):
        mask = 0
        for r in range(rows):
            mask |= 1 << (c * (rows + 1) + r)
        COLUMN_MASKS[c] = mask

    CENTER_MASK = COLUMN_MASKS[cols // 2]            # finds the center column and stores its mask.

    # horizontal
    for r in range(rows):
        for c in range(cols - 3):
            mask = 0
            for i in range(4):
                mask |= 1 << ((c + i) * (rows + 1) + r)
            WINDOW_MASKS.append(mask)
    # vertical
    for c in range(cols):
        for r in range(rows - 3):
            mask = 0
            for i in range(4):
                mask |= 1 << (c * (rows + 1) + (r + i))
            WINDOW_MASKS.append(mask)
    # diag \
    for r in range(rows - 3):
        for c in range(cols - 3):
            mask = 0
            for i in range(4):
                mask |= 1 << ((c + i) * (rows + 1) + (r + i))
            WINDOW_MASKS.append(mask)
    # diag /
    for r in range(3, rows):
        for c in range(cols - 3):
            mask = 0
            for i in range(4):
                mask |= 1 << ((c + i) * (rows + 1) + (r - i))
            WINDOW_MASKS.append(mask)


# counts number of 1 bits (pieces) in a board integer
def popcount(x):
    return x.bit_count()

# Checks the percentage of filled cells
def get_game_phase(board_obj):
    rows, cols = board_obj.rows, board_obj.cols
    total_cells = rows * cols
    filled = popcount(board_obj.board_p1 | board_obj.board_p2)
    fill_ratio = filled / total_cells
    if fill_ratio < 0.33:
        return "early"
    if fill_ratio < 0.66:
        return "mid"
    return "late"

# Return weights for each possible move based on the percentage fill
def get_dynamic_weights(phase):
    if phase == "early":
        return {"center": 6, "bottom": 2, "two": 4, "three": 8, "four": 10000, "block_three": 10}
    if phase == "mid":
        return {"center": 5, "bottom": 3, "two": 6, "three": 20, "four": 10000, "block_three": 30}
    return {"center": 4, "bottom": 1, "two": 2, "three": 40, "four": 10000, "block_three": 60}

# counts how many of player's or opponent's pieces are in a single cell window 
# Adds or subtracts from the score based on the counted pieces 
def evaluate_window(window_mask, piece, weights):
    if isinstance(piece, tuple) and len(piece) == 2:
        player_bits, opp_bits = piece
    else:
        return 0
    player_count = popcount(player_bits & window_mask)
    opp_count = popcount(opp_bits & window_mask)
    empty_count = 4 - player_count - opp_count
    score = 0
    if player_count == 4:
        score += weights["four"]
    elif player_count == 3 and empty_count == 1:
        score += weights["three"]
    elif player_count == 2 and empty_count == 2:
        score += weights["two"]
    if opp_count == 3 and empty_count == 1:
        score -= weights["block_three"]
    return score

# Calculates and returns the score for a single player 
def single_player_score(board_obj, piece, weights):
    global WINDOW_MASKS, CENTER_MASK, COLUMN_MASKS
    if WINDOW_MASKS is None:
        precompute_window_masks(board_obj.rows, board_obj.cols)
    my_board = board_obj.board_p1 if piece == PLAYER_PIECE else board_obj.board_p2
    opp_board = board_obj.board_p1 if piece == AI_PIECE else board_obj.board_p2
    score = 0
    rows, cols = board_obj.rows, board_obj.cols

    # Center control
    center_count = popcount(my_board & CENTER_MASK)
    score += center_count * weights["center"]

    # Bottom bias
    for c in range(cols):
        for r in range(rows):
            bit = 1 << (c * (rows + 1) + r)
            if my_board & bit:
                score += r * weights["bottom"]

    # Window evaluations
    for mask in WINDOW_MASKS:
        score += evaluate_window(mask, (my_board, opp_board), weights)
    return score

def get_agg(phase):
    if phase == "early":
        return 0.8    # be more aggressive in the begining 
    if phase == "mid":
        return 1.0
    return 1.2   # be more defensive late game

# returns the final score for a board for a piece dropped
def score_position(board_obj, piece):
    phase = get_game_phase(board_obj)
    weights = get_dynamic_weights(phase)
    opp_piece = PLAYER_PIECE if piece == AI_PIECE else AI_PIECE
    my_score = single_player_score(board_obj, piece, weights)
    opp_score = single_player_score(board_obj, opp_piece, weights)
    agg = get_agg(phase)
    return my_score - agg * opp_score

# counts number of 4-in-a-rows horizontally, vertically, and diagonally.
def count_connect_fours(board_obj, piece):
    board = board_obj.get_board_array()
    rows, cols = len(board), len(board[0])
    cnt = 0
    for r in range(rows):
        for c in range(cols - 3):
            if all(board[r][c + i] == piece for i in range(4)):
                cnt += 1
    for c in range(cols):
        for r in range(rows - 3):
            if all(board[r + i][c] == piece for i in range(4)):
                cnt += 1
    for r in range(rows - 3):
        for c in range(cols - 3):
            if all(board[r + i][c + i] == piece for i in range(4)):
                cnt += 1
    for r in range(3, rows):
        for c in range(cols - 3):
            if all(board[r - i][c + i] == piece for i in range(4)):
                cnt += 1
    return cnt

# check for the board if full 
def is_terminal_node(board_obj):
    return board_obj.is_full()

# returns a dict {column: probability} for expected minimax
# models chance that a piece may land left/right of intended column
def compute_probabilities(board_obj, intended_col):
    valid = board_obj.get_valid_locations()
    left = intended_col - 1
    right = intended_col + 1
    if left in valid and right in valid:
        return {left: 0.2, intended_col: 0.6, right: 0.2}
    if left not in valid and right in valid:
        return {intended_col: 0.6, right: 0.4}
    if right not in valid and left in valid:
        return {left: 0.4, intended_col: 0.6}
    return {intended_col: 1.0}

# ==============================
# NODE CREATION
# ==============================
# represents a node in the search tree. 
class Node:
    def __init__(self, board, col=None, score=None, node_type=None, probabilities=None):
        self.board = board
        self.col = col
        self.score = score
        self.node_type = node_type       # "max", "min", "chance", "terminal"
        self.probabilities = probabilities
        self.children = []
        self.expanded = True


def order_moves(board_obj, valid_locations, maximizingPlayer):
    # center-first baseline order
    cols = board_obj.cols
    center = cols // 2
    # score using center proximity
    ordered = sorted(valid_locations, key=lambda c: abs(c - center))
    # quick promotion: if playing AI, check if a drop in col gives more connect_fours for AI,
    # or if opponent will get immediate 3->4 we can block. This is only an ordering heuristic.
    promoted = []
    rest = []
    for c in ordered:
        temp = board_obj.copy()
        temp.drop_piece(c, AI_PIECE if maximizingPlayer else PLAYER_PIECE)
        # use same count_connect_fours function (cached board arrays) - keeps exact behavior
        my_fours = count_connect_fours(temp, AI_PIECE if maximizingPlayer else PLAYER_PIECE)
        if my_fours > count_connect_fours(board_obj, AI_PIECE if maximizingPlayer else PLAYER_PIECE):
            promoted.append(c)
        else:
            rest.append(c)
    # final order: promoted moves (likely good) then the rest (center-biased)
    return promoted + rest

# ==============================
# MINIMAX
# ==============================
def minimax_tree(board_obj, depth, maximizingPlayer, parent= None):
    search_key = (board_obj.board_p1, board_obj.board_p2, depth, maximizingPlayer, 'minimax')
    global expanded_nodes_count

    # if the exact board is in the cache, we only return the cached result to avoid re-computations 
    if search_key in _search_cache:
        cached = _search_cache[search_key]
        node = Node(board_obj.copy(), col=cached['best_col'], score=cached['score'], node_type=cached['node_type'])
        node.expanded = cached.get('expanded', True)
        # Generate children if cached children exist
        if 'children' in cached:
            for c in cached['children']:
                child_node = Node(c['board'], col=c.get('col'), score=c.get('score'), node_type=c.get('node_type'))
                node.children.append(child_node)
        if parent:
            parent.children.append(node)
        return node, node.score
    
    valid_locations = board_obj.get_valid_locations()
    if depth == 0 or is_terminal_node(board_obj):
        score = score_position(board_obj, AI_PIECE)
        node = Node(board_obj.copy(), score=score, node_type="terminal")
        if parent:
            parent.children.append(node)
        # Store in cache
        _search_cache[search_key] = {'score': score, 'best_col': None, 'node_type': 'terminal', 'children': []}
        expanded_nodes_count += 1
        return node, score
    children_data = []

    if maximizingPlayer:
        value = -math.inf               # as we want to reach highest possible score
        best_col = random.choice(valid_locations)
        node = Node(board_obj.copy(), node_type="max") 
        expanded_nodes_count += 1
        if parent and node:
            parent.children.append(node)
        for col in valid_locations:
            b_copy = board_obj.copy()
            # simulate move
            b_copy.drop_piece(col, AI_PIECE)
            child_node, new_score = minimax_tree(b_copy, depth - 1, False, node)
            if new_score > value:
                value = new_score
                best_col = col

            children_data.append({'board': b_copy.copy(),'col': col,'score': new_score,'node_type': child_node.node_type})
        node.col = best_col
        node.score = value
        # after computing the values of the node expanded, we store it in the cache
        _search_cache[search_key] = {'score': value,'best_col': best_col,'node_type': "max",'children': children_data,'expanded': node.expanded}
        return node, value
    else:
        value = math.inf                      # as we want to reach lowest possible score
        best_col = random.choice(valid_locations)
        node = Node(board_obj.copy(), node_type="min")
        expanded_nodes_count += 1
        if parent and node:
            parent.children.append(node)
        for col in valid_locations:
            b_copy = board_obj.copy()
            b_copy.drop_piece(col, PLAYER_PIECE)
            child_node, new_score = minimax_tree(b_copy, depth - 1, True, node)
            if new_score < value:
                value = new_score
                best_col = col
            children_data.append({'board': b_copy.copy(),'col': col,'score': new_score,'node_type': child_node.node_type})

        node.col = best_col
        node.score = value
        _search_cache[search_key] = {'score': value,'best_col': best_col,'node_type': "min",'children': children_data,'expanded': node.expanded}
        return node , value


# ==============================
# MINIMAX WITH ALPHA-BETA PRUNING
# ==============================
def minimax_alpha_beta_tree(board_obj, depth, alpha, beta, maximizingPlayer, parent=None):
    search_key = (board_obj.board_p1, board_obj.board_p2, depth, maximizingPlayer, 'alphabeta')
    global expanded_nodes_count
    # Check cache
    if search_key in _search_cache:
        cached = _search_cache[search_key]
        node = Node(board_obj.copy(), col=cached['best_col'], score=cached['score'], node_type=cached['node_type'])
        node.expanded = cached.get('expanded', True)
        # Reconstruct children
        if 'children' in cached:
            for c in cached['children']:
                child_node = Node(c['board'], col=c.get('col'), score=c.get('score'), node_type=c.get('node_type'))
                node.children.append(child_node)

        if parent:
            parent.children.append(node)
        return node, node.score

    valid_locations = board_obj.get_valid_locations()
    if depth == 0 or is_terminal_node(board_obj):
        score = score_position(board_obj, AI_PIECE)
    
        node = Node(board_obj.copy(), score=score)
        if parent:
            parent.children.append(node)
        _search_cache[search_key] = {'score': score, 'best_col': None, 'node_type': 'terminal', 'children': []}
        expanded_nodes_count += 1
        return node, score
    
    # order the nodes to allow max pruning 
    ordered_locations = order_moves(board_obj, valid_locations, maximizingPlayer)
    children_data= []
    if maximizingPlayer:
        value = -math.inf
        best_col = random.choice(ordered_locations) if ordered_locations else None
        node = Node(board_obj.copy(), node_type="max") 
        if parent and node:
            parent.children.append(node)
        expanded_nodes_count += 1
        for col in ordered_locations:
            # simulate move
            b_copy = board_obj.copy()
            b_copy.drop_piece(col, AI_PIECE)
            child_node, new_score = minimax_alpha_beta_tree(b_copy, depth - 1, alpha, beta, False, node)
            if new_score > value:
                value = new_score
                best_col = col
            alpha = max(alpha, value)             # updated in max nodes
            children_data.append({'board': b_copy.copy(),'col': col,'score': new_score,'node_type': child_node.node_type})
            if alpha >= beta:
                break

        node.col = best_col
        node.score = value

        _search_cache[search_key] = {'score': value,'best_col': best_col,'node_type': "max",'children': children_data,'expanded': node.expanded}
        return node, value

    else:
        value = math.inf
        best_col = random.choice(ordered_locations) if ordered_locations else None
        node = Node(board_obj.copy(), node_type="min") 
        if parent and node:
            parent.children.append(node)
        expanded_nodes_count += 1
        for col in ordered_locations:
            b_copy = board_obj.copy()
            b_copy.drop_piece(col, PLAYER_PIECE)
            child_node, new_score = minimax_alpha_beta_tree(b_copy, depth - 1, alpha, beta, True, node)
            if new_score < value:
                value = new_score
                best_col = col
            beta = min(beta, value)             # updated in min nodes
            children_data.append({'board': b_copy.copy(),'col': col,'score': new_score,'node_type': child_node.node_type})
            if alpha >= beta:
                break

        node.col = best_col
        node.score = value

        _search_cache[search_key] = {'score': value,'best_col': best_col,'node_type': "min",'children': children_data,'expanded': node.expanded}
        return node, value


# ==============================
# EXPECTED MINIMAX
# ==============================
def expected_minimax_tree(board_obj, depth, start_max=True, parent=None):
    # computes the score for the leaf node
    def eval_node(b, par):
        sc = score_position(b, AI_PIECE)
        leaf = Node(b.copy(), score=sc, node_type="terminal")
        if par:
            par.children.append(leaf)
        return leaf, sc

    def exp(board, depth, node_type, par):
        global expanded_nodes_count
        if depth <= 0 or is_terminal_node(board):
            return eval_node(board, par)

        valid = board.get_valid_locations()
        if not valid:
            return eval_node(board, par)

        if node_type in ("max", "min"):
            maximizing = (node_type == "max")
            node = Node(board.copy(), node_type=node_type)
            if par:
                par.children.append(node)

            best_val = -math.inf if maximizing else math.inf
            best_col = valid[0]

            for intended_col in valid:
                chance = Node(board.copy(), node_type="chance")      # chance nodes introduced 
                probs = compute_probabilities(board, intended_col)   # each child has a probability of occuring
                chance.probabilities = probs
                node.children.append(chance)

                if depth - 1 <= 0:
                    exp_val = 0.0
                    # loops over all possible outcomes for the intended column
                    for actual_col, p in probs.items():
                        b2 = board.copy()
                        if b2.is_valid_location(actual_col):
                            b2.drop_piece(actual_col, AI_PIECE if maximizing else PLAYER_PIECE)
                        # multiply the score by the probability of this outcome
                        # will keep summing this value for all possibilities 
                        exp_val += p * score_position(b2, AI_PIECE)
                        expanded_nodes_count += 1   
                    chance.score = exp_val
                else:
                    exp_val = 0.0
                    next_type = "min" if maximizing else "max"
                    for actual_col, p in probs.items():
                        b2 = board.copy()
                        if b2.is_valid_location(actual_col):
                            b2.drop_piece(actual_col, AI_PIECE if maximizing else PLAYER_PIECE)
                        _, val = exp(b2, depth - 2, next_type, chance)
                        expanded_nodes_count += 1
                        exp_val += p * val
                    chance.score = exp_val
                
                # after computing expected value, update the best expected score and move
                if maximizing:
                    if exp_val > best_val:
                        best_val, best_col = exp_val, intended_col
                else:
                    if exp_val < best_val:
                        best_val, best_col = exp_val, intended_col

            node.col = best_col
            node.score = best_val
            return node, best_val

        return eval_node(board, par)

    root_type = "max" if start_max else "min"
    return exp(board_obj, depth, root_type, parent)

# simulates piece falling probabilistically
def probabilistic_drop(board_obj, intended_col, piece):
    valid_locations = board_obj.get_valid_locations()
    neighbors = []
    # checking if the left neighbor is valid
    if intended_col - 1 in valid_locations:
        neighbors.append(intended_col - 1)
     # checking if the right neighbor is valid
    if intended_col + 1 in valid_locations:
        neighbors.append(intended_col + 1)
    # probabilities are assigned depending on the number of neighbors available 
    if len(neighbors) == 2:        # left and right columns exist
        probs = [0.2, 0.6, 0.2]
        drop_cols = [neighbors[0], intended_col, neighbors[1]]
    elif len(neighbors) == 1:         # Only left or only right exist
        probs = [0.4, 0.6]
        drop_cols = [neighbors[0], intended_col] if neighbors[0] < intended_col else [intended_col, neighbors[0]]
    else:                            # None exists 
        probs = [1.0]
        drop_cols = [intended_col]
    r = random.random()           # generate a random number from 0 to 1
    cumulative = 0
    selected_col = drop_cols[-1]
    for col, prob in zip(drop_cols, probs):
        cumulative += prob            # add probabilities until we exceed the random number
        if r <= cumulative:
            selected_col = col        # the matching column is selected
            break
    return selected_col

# ==============================
# DRAWING & LAYOUT HELPERS
# ==============================

# computes how big every cell should be and where the board should be placed inside a rectangle.
def compute_grid_geom(board_rect, rows, cols):
    square = min(board_rect.width // cols, board_rect.height // rows)
    total_w = cols * square
    total_h = rows * square
    offset_x = board_rect.left + (board_rect.width - total_w) // 2
    offset_y = board_rect.top + (board_rect.height - total_h) // 2
    return square, offset_x, offset_y
# allows collapsing/expanding subtrees visually
def _visible_children(node):
    if node is None:
        return []
    return node.children if getattr(node, "expanded", True) else []

# draws the Connect 4 board and the pieces.
def draw_board(screen, board_obj, board_rect, player_color, ai_color):
    board = board_obj.get_board_array
    board = board_obj.get_board_array()
    rows, cols = len(board), len(board[0])
    SQUARESIZE, offset_x, offset_y = compute_grid_geom(board_rect, rows, cols)
    RADIUS = SQUARESIZE // 2 - 6

    total_w = cols * SQUARESIZE
    total_h = rows * SQUARESIZE
    frame_rect = pygame.Rect(offset_x - 10, offset_y - 10, total_w + 20, total_h + 20)
    pygame.draw.rect(screen, BLUE, frame_rect, border_radius=18)

    for c in range(cols):
        for r in range(rows):
            cx = offset_x + c * SQUARESIZE + SQUARESIZE // 2
            cy = offset_y + (rows - 1 - r) * SQUARESIZE + SQUARESIZE // 2
            pygame.draw.circle(screen, BLACK, (cx, cy), RADIUS + 4)
            pygame.draw.circle(screen, (235, 235, 235), (cx, cy), RADIUS + 2)
            if board[r][c] == PLAYER_PIECE:
                pygame.draw.circle(screen, player_color, (cx, cy), RADIUS)
            elif board[r][c] == AI_PIECE:
                pygame.draw.circle(screen, ai_color, (cx, cy), RADIUS)

    pygame.draw.rect(
        screen,
        (50, 50, 50),
        (frame_rect.left + 5, frame_rect.bottom, frame_rect.width - 10, 6),
        border_radius=3,
    )
# draws the top bar with: Undo /Restart /Exit buttons, "PLAYER TURN" or "AI TURN", colored disc showing whose turn, timer
def draw_player_panel(screen, rect, turn, player_color, ai_color, timer_seconds, font, ui):
    pygame.draw.rect(screen, PANEL_BG, rect, border_radius=12)
    pygame.draw.rect(screen, PANEL_BORDER, rect, 1, border_radius=12)

    icon_size = ui["ICON_SIZE"]
    icon_gap = ui["ICON_GAP"]
    icon_pad = ui["ICON_PAD"]

    icons = ["UNDO", "RESTART", "EXIT"]
    icon_rects = []
    x = rect.right - icon_size - icon_pad
    y = rect.top + icon_pad
    for label in reversed(icons):
        r = pygame.Rect(x, y, icon_size, icon_size)
        pygame.draw.rect(screen, (24, 24, 24), r, border_radius=8)
        pygame.draw.rect(screen, (90, 90, 90), r, 1, border_radius=8)
        t = font.render(label[0], True, (210, 210, 210))
        screen.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))
        icon_rects.append((label, r))
        x -= icon_size + icon_gap

    pill_w, pill_h = ui["TURN_PILL_W"], ui["TURN_PILL_H"]
    pill = pygame.Rect(rect.left + (rect.width - pill_w) // 2, rect.top + ui["TURN_PILL_TOP"], pill_w, pill_h)
    pygame.draw.rect(screen, (32, 32, 32), pill, border_radius=18)
    turn_text = "PLAYER TURN" if turn == PLAYER else "AI TURN"
    tt = font.render(turn_text, True, WHITE)
    screen.blit(tt, (pill.centerx - tt.get_width() // 2, pill.centery - tt.get_height() // 2))

    disc_y = pill.bottom + 36
    disc_x = pill.centerx
    disc_color = player_color if turn == PLAYER else ai_color
    pygame.draw.circle(screen, disc_color, (disc_x, disc_y), 20)

    timer_font = pygame.font.SysFont("monospace", 28)
    timer_text = timer_font.render(f"{timer_seconds:02d}s", True, MUTED)
    screen.blit(timer_text, (pill.centerx - timer_text.get_width() // 2, disc_y + 28))

    return icon_rects

# used to scale spacing and background shading
def _measure_tree(root, max_level, level=0):
    children = _visible_children(root)
    if root is None or level >= max_level or not children:
        return 1, level
    leaves = 0
    deepest = level
    for ch in children:
        l, d = _measure_tree(ch, max_level, level + 1)
        leaves += l
        deepest = max(deepest, d)
    return max(1, leaves), deepest

# It recursively assigns an x,y coordinate to every visible node.
# Leaf nodes get placed from left to right.
# Internal nodes get centered above their children
def _assign_positions(root, x0, y0, x_spacing, y_spacing,
                      max_level, level=0, next_x=None, pos=None):
    if next_x is None:
        next_x = [0]
    if pos is None:
        pos = {}
    if root is None:
        return pos

    children = _visible_children(root)

    if level >= max_level or not children:
        x = x0 + next_x[0] * x_spacing
        y = y0 + level * y_spacing
        pos[id(root)] = (x, y)
        next_x[0] += 1
        return pos

    for ch in children:
        _assign_positions(ch, x0, y0, x_spacing, y_spacing,
                          max_level, level + 1, next_x, pos)

    xs = [pos[id(ch)][0] for ch in children]
    px = (min(xs) + max(xs)) // 2
    py = y0 + level * y_spacing
    pos[id(root)] = (px, py)
    return pos

# draws curved connecting lines between parent and child nodes
def _draw_bezier(surface, p0, p1, color, width=1, steps=16):
    midx = (p0[0] + p1[0]) / 2
    c1 = (midx, p0[1]); c2 = (midx, p1[1])
    points = []
    for i in range(steps + 1):
        t = i / steps
        if t <= 0.5:
            tt = t * 2
            a0 = (p0[0]*(1-tt)+c1[0]*tt, p0[1]*(1-tt)+c1[1]*tt)
            m = (midx, (p0[1]+p1[1])/2)
            a1 = (c1[0]*(1-tt)+m[0]*tt, c1[1]*(1-tt)+m[1]*tt)
            pt = (a0[0]*(1-tt)+a1[0]*tt, a0[1]*(1-tt)+a1[1]*tt)
        else:
            tt = (t-0.5)*2
            m = (midx, (p0[1]+p1[1])/2)
            a0 = (m[0]*(1-tt)+c2[0]*tt, m[1]*(1-tt)+c2[1]*tt)
            a1 = (c2[0]*(1-tt)+p1[0]*tt, c2[1]*(1-tt)+p1[1]*tt)
            pt = (a0[0]*(1-tt)+a1[0]*tt, a0[1]*(1-tt)+a1[1]*tt)
        points.append((int(pt[0]), int(pt[1])))
    pygame.draw.aalines(surface, color, False, points)

# ==============================
# WORLD CAMERA (no pre-surface)
# ==============================
# camera state
tree_zoom = 1.0           # zooming with mouse wheel
tree_pan_x = 0            # dragging tree with mouse
tree_pan_y = 0

_tree_pos_world = {}           # id(node) -> (x,y)
_tree_hitboxes_world = []      # [(node, pygame.Rect in world)]
_world_bounds = (0,0,1,1)

# converts from mouse click to tree positions
def screen_to_world(tree_rect, sx, sy):
    lx = sx - tree_rect.left
    ly = sy - tree_rect.top
    if tree_zoom == 0:
        return 0, 0
    wx = (lx - tree_pan_x) / tree_zoom
    wy = (ly - tree_pan_y) / tree_zoom
    return wx, wy

def _layout_tree_world(root, x_spacing, y_spacing, max_levels):
    if root is None:
        return {}, (0,0,1,1)
    left_pad, top_pad = TREE_LEFT_PAD, TREE_TOP_PAD
    pos = _assign_positions(root, left_pad, top_pad, x_spacing, y_spacing, max_levels)
    xs, ys = [], []
    for (x, y) in pos.values():
        xs.append(x); ys.append(y)
    if not xs:
        return {}, (0,0,1,1)
    minx = min(xs) - 200
    maxx = max(xs) + 200
    miny = min(ys) - 120
    maxy = max(ys) + 200
    return pos, (minx, miny, maxx, maxy)

def _draw_tree_viewport(screen, tree_rect, root, font,
                        x_spacing, y_spacing, max_levels):
    global _tree_pos_world, _world_bounds, _tree_hitboxes_world

    _tree_pos_world, _world_bounds = _layout_tree_world(root, x_spacing, y_spacing, max_levels)
    _tree_hitboxes_world = []

    viewport = pygame.Surface((tree_rect.width, tree_rect.height))
    viewport.fill((8, 8, 8))

    def to_screen(p):
        wx, wy = p
        sx = int((wx * tree_zoom) + tree_pan_x)
        sy = int((wy * tree_zoom) + tree_pan_y)
        return sx, sy

    _, deepest = _measure_tree(root, max_levels)
    band_col = (14, 14, 14)
    for lvl in range(0, min(max_levels, deepest) + 1):
        y_world = TREE_TOP_PAD + lvl * y_spacing - 34
        y_scr = int(y_world * tree_zoom + tree_pan_y)
        pygame.draw.rect(viewport, band_col, pygame.Rect(0, y_scr, tree_rect.width, int(y_spacing * tree_zoom)))

    COLOR_LINE = (200, 200, 200)
    def _walk_edges(n):
        chs = _visible_children(n)
        if not n or not chs:
            return
        x0, y0 = _tree_pos_world[id(n)]
        for ch in chs:
            x1, y1 = _tree_pos_world[id(ch)]
            p0 = to_screen((x0, y0 + 16))
            p1 = to_screen((x1, y1 - 16))
            _draw_bezier(viewport, p0, p1, COLOR_LINE, 1)
            _walk_edges(ch)
    _walk_edges(root)
    # change colour of node based on it's type
    def _node_color(nt):
        return (50,200,80) if nt=="max" else (225,65,65) if nt=="min" \
               else (65,145,240) if nt=="chance" else (120,120,120) if nt=="terminal" \
               else (100,100,100)

    id2node = {}
    def _map(n):
        if not n: return
        id2node[id(n)] = n
        for ch in _visible_children(n): _map(ch)
    _map(root)

    for node_id, (nx, ny) in _tree_pos_world.items():
        n = id2node[node_id]
        display_col = "-" if n.col is None else (n.col + 1)
        label = f"{display_col} | {('-' if n.score is None else round(n.score, 2))}"

        if _visible_children(n):
            ind = "▼" if getattr(n, "expanded", True) else "▶"
            label = ind + " " + label

        text_surf = font.render(label, True, (255,255,255))
        node_w = max(72, text_surf.get_width() + 24)
        node_h = 28
        rect_world = pygame.Rect(int(nx - node_w/2), int(ny - node_h/2), node_w, node_h)
        _tree_hitboxes_world.append((n, rect_world.copy()))

        tl = to_screen(rect_world.topleft)
        br = to_screen(rect_world.bottomright)
        rect_screen = pygame.Rect(tl[0], tl[1], br[0]-tl[0], br[1]-tl[1])

        shadow = rect_screen.copy(); shadow.x += 2; shadow.y += 2
        pygame.draw.rect(viewport, (30,30,30), shadow, border_radius=10)

        color = _node_color(n.node_type)
        if n.node_type == "max":        # triangle pointing upward 
            p1 = (rect_screen.centerx, rect_screen.top)
            p2 = (rect_screen.left, rect_screen.bottom)
            p3 = (rect_screen.right, rect_screen.bottom)
            pygame.draw.polygon(viewport, color, (p1,p2,p3))
        elif n.node_type == "min":      # triangle pointing downward 
            p1 = (rect_screen.left, rect_screen.top)
            p2 = (rect_screen.right, rect_screen.top)
            p3 = (rect_screen.centerx, rect_screen.bottom)
            pygame.draw.polygon(viewport, color, (p1,p2,p3))
        else:                           # terminal node
            pygame.draw.rect(viewport, color, rect_screen, border_radius=10)

        viewport.blit(text_surf, (rect_screen.centerx - text_surf.get_width()//2,
                                  rect_screen.centery - text_surf.get_height()//2))

        if n.node_type == "chance" and getattr(n,"probabilities",None):
            ptxt = font.render(str(n.probabilities), True, (245,220,70))
            viewport.blit(ptxt, (rect_screen.centerx - ptxt.get_width()//2, rect_screen.bottom + 4))

    screen.blit(viewport, tree_rect.topleft)
# initializes which nodes are expanded at the start
def init_tree_expansion(root, max_open_depth=1):
    def dfs(n, depth):
        if n is None: return
        n.expanded = (depth <= max_open_depth)
        for ch in n.children:
            dfs(ch, depth + 1)
    dfs(root, 0)

# ===================
# MENUS
# ===================
# draws a vertical gradient background.
def vgradient(surface, top_color, bottom_color):
    h = surface.get_height()
    for y in range(h):
        t = y / max(h - 1, 1)
        c = (
            int(top_color[0] * (1 - t) + bottom_color[0] * t),
            int(top_color[1] * (1 - t) + bottom_color[1] * t),
            int(top_color[2] * (1 - t) + bottom_color[2] * t),
        )
        pygame.draw.line(surface, c, (0, y), (surface.get_width(), y))
# draws a semi-transparent “glass” UI panel.
def draw_glass_card(surf, rect, alpha=140):
    overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    overlay.fill((255, 255, 255, alpha))
    surf.blit(overlay, rect.topleft)
    pygame.draw.rect(surf, (255, 255, 255, 40), rect, 1, border_radius=16)
# button renderer
def button(surf, rect, label, font, base=(30, 30, 30), hover=(60, 60, 60),
           text_col=(240, 240, 240), mouse=None):
    if mouse is None:
        mouse = pygame.mouse.get_pos()
    is_hover = rect.collidepoint(mouse)
    col = hover if is_hover else base
    pygame.draw.rect(surf, col, rect, border_radius=12)
    pygame.draw.rect(surf, (90, 90, 90), rect, 1, border_radius=12)
    txt = font.render(label, True, text_col)
    surf.blit(txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2))
    return is_hover
# shows a menu to choose red or yellow
def draw_color_menu(screen, width, height):
    title_font = pygame.font.SysFont("monospace", 56, bold=True)
    small = pygame.font.SysFont("monospace", 22)
    clock = pygame.time.Clock()
    chosen_color = None
    t0 = time.time()
    card = pygame.Rect(width // 2 - 420, height // 2 - 200, 840, 400)
    red_btn = pygame.Rect(card.left + 120, card.bottom - 120, 220, 56)
    yel_btn = pygame.Rect(card.right - 120 - 220, card.bottom - 120, 220, 56)
    while chosen_color is None:
        vgradient(screen, (15, 20, 45), (10, 10, 14))
        now = time.time() - t0
        cx1 = width // 2 - 160
        cy = height // 2 - 40 + int(10 * math.sin(now * 2.0))
        cx2 = width // 2 + 160
        pygame.draw.circle(screen, RED, (cx1, cy), 52)
        pygame.draw.circle(screen, YELLOW, (cx2, cy), 52)
        pygame.draw.circle(screen, (230, 230, 230), (cx1, cy), 50, 3)
        pygame.draw.circle(screen, (230, 230, 230), (cx2, cy), 50, 3)
        draw_glass_card(screen, card, 120)
        title = title_font.render("Pick Your Team", True, (245, 245, 245))
        screen.blit(title, (card.centerx - title.get_width() // 2, card.top + 26))
        button(screen, red_btn, "Play RED  (R)", small, base=(40, 20, 20), hover=(90, 30, 30))
        button(screen, yel_btn, "Play YELLOW (Y)", small, base=(60, 60, 20), hover=(120, 120, 40))
        hint = small.render("Click a token or button · Press R/Y · ESC to quit", True, (210, 210, 210))
        screen.blit(hint, (card.centerx - hint.get_width() // 2, card.bottom - 50))
        pygame.display.flip()
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key in (pygame.K_r, pygame.K_RSHIFT):
                    chosen_color = RED
                elif event.key in (pygame.K_y,):
                    chosen_color = YELLOW
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if (mx - cx1) ** 2 + (my - cy) ** 2 <= 50 ** 2 or red_btn.collidepoint(event.pos):
                    chosen_color = RED
                elif (mx - cx2) ** 2 + (my - cy) ** 2 <= 50 ** 2 or yel_btn.collidepoint(event.pos):
                    chosen_color = YELLOW
    return chosen_color
# allows the player to choose the number of rows and columns 
def draw_board_size_menu(screen, width, height):
    title_font = pygame.font.SysFont("monospace", 52, bold=True)
    small = pygame.font.SysFont("monospace", 24)
    clock = pygame.time.Clock()
    rows, cols = 6, 7
    choosing = True
    card = pygame.Rect(width // 2 - 520, height // 2 - 260, 1040, 570)
    start_btn = pygame.Rect(card.centerx - 140, card.bottom - 100, 280, 56)
    minus_r = pygame.Rect(card.left + 140, card.top + 200, 44, 44)
    plus_r = pygame.Rect(card.left + 340, card.top + 200, 44, 44)
    minus_c = pygame.Rect(card.left + 620, card.top + 200, 44, 44)
    plus_c = pygame.Rect(card.left + 820, card.top + 200, 44, 44)

    def clamp_vals():
        nonlocal rows, cols
        rows = max(4, min(10, rows))
        cols = max(4, min(10, cols))

    while choosing:
        vgradient(screen, (12, 16, 28), (9, 9, 12))
        draw_glass_card(screen, card, 110)
        title = title_font.render("Board Setup", True, (245, 245, 245))
        screen.blit(title, (card.centerx - title.get_width() // 2, card.top + 24))
        label_r = small.render("Rows", True, (240, 240, 240))
        label_c = small.render("Columns", True, (240, 240, 240))
        screen.blit(label_r, (card.left + 140, card.top + 160))
        screen.blit(label_c, (card.left + 620, card.top + 160))
        val_r = small.render(str(rows), True, YELLOW)
        val_c = small.render(str(cols), True, YELLOW)
        screen.blit(val_r, (card.left + 240 - val_r.get_width() // 2, card.top + 206))
        screen.blit(val_c, (card.left + 720 - val_c.get_width() // 2, card.top + 206))
        button(screen, minus_r, "-", small)
        button(screen, plus_r, "+", small)
        button(screen, minus_c, "-", small)
        button(screen, plus_c, "+", small)
        preview = pygame.Rect(card.left + 80, card.top + 290, card.width - 160, 160)
        pygame.draw.rect(screen, (25, 48, 120), preview, border_radius=14)
        if cols > 0 and rows > 0:
            cell = min((preview.width - 20) // cols, (preview.height - 20) // rows)
            ox = preview.left + (preview.width - cols * cell) // 2
            oy = preview.top + (preview.height - rows * cell) // 2
            rad = cell // 2 - 2
            for cc in range(cols):
                for rr in range(rows):
                    cx = ox + cc * cell + cell // 2
                    cy = oy + (rows - 1 - rr) * cell + cell // 2
                    pygame.draw.circle(screen, (230, 230, 230), (cx, cy), rad)
        button(screen, start_btn, "Start Game", small, base=(40, 70, 160), hover=(60, 100, 220))
        hint = small.render("Use +/- keys or click buttons · ESC to quit", True, (210, 210, 210))
        screen.blit(hint, (card.centerx - hint.get_width() // 2, card.bottom - 46))
        pygame.display.flip()
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key in (pygame.K_PLUS, pygame.K_EQUALS):
                    rows += 1
                if event.key == pygame.K_MINUS:
                    rows -= 1
                if event.key == pygame.K_RIGHT:
                    cols += 1
                if event.key == pygame.K_LEFT:
                    cols -= 1
                clamp_vals()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if minus_r.collidepoint(event.pos): rows -= 1
                elif plus_r.collidepoint(event.pos): rows += 1
                elif minus_c.collidepoint(event.pos): cols -= 1
                elif plus_c.collidepoint(event.pos): cols += 1
                elif start_btn.collidepoint(event.pos): choosing = False
                clamp_vals()

    return rows, cols
# allows the player to choose the solver type and the search depth for the solver 
def draw_ai_settings_menu(screen, width, height):
    font = pygame.font.SysFont("monospace", 40)
    small_font = pygame.font.SysFont("monospace", 30)
    solver_options = ["Minimax", "Alpha-Beta", "Expected Minimax"]
    solver_index = 1
    depth = 4
    choosing = True
    card = pygame.Rect(width // 2 - 520, height // 2 - 220, 1040, 440)
    toggle_rect = pygame.Rect(card.centery + 350, card.centery - 30, 300, 44)
    up_depth = pygame.Rect(card.centerx + 220, card.centery + 20, 44, 44)
    down_depth = pygame.Rect(card.centerx + 150, card.centery + 20, 44, 44)
    start_rect = pygame.Rect(card.centerx - 140, card.bottom - 90, 280, 56)

    while choosing:
        vgradient(screen, (10, 15, 25), (8, 8, 12))
        draw_glass_card(screen, card, 110)
        title = font.render("AI Settings", True, (245, 245, 245))
        screen.blit(title, (card.centerx - title.get_width() // 2, card.top + 26))
        alg_label = small_font.render("Solver:", True, WHITE)
        alg_value = small_font.render(solver_options[solver_index], True, YELLOW)
        screen.blit(alg_label, (card.left + 160, card.centery - 20))
        screen.blit(alg_value, (card.left + 300, card.centery - 20))
        button(screen, toggle_rect, "Toggle Solver", small_font, base=(40, 70, 160), hover=(60, 100, 220))
        depth_label = small_font.render("Depth:", True, WHITE)
        depth_value = small_font.render(str(depth), True, YELLOW)
        screen.blit(depth_label, (card.left + 160, card.centery + 40))
        screen.blit(depth_value, (card.left + 300, card.centery + 40))
        button(screen, up_depth, "+", small_font)
        button(screen, down_depth, "-", small_font)
        button(screen, start_rect, "Continue", small_font, base=(40, 120, 60), hover=(60, 180, 90))
        pygame.display.update()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if toggle_rect.collidepoint(event.pos): solver_index = (solver_index + 1) % len(solver_options)
                elif up_depth.collidepoint(event.pos): depth = min(15, depth + 1)
                elif down_depth.collidepoint(event.pos): depth = max(1, depth - 1)
                elif start_rect.collidepoint(event.pos): choosing = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: pygame.quit(); sys.exit()
                if event.key in (pygame.K_RIGHT, pygame.K_LEFT): solver_index = (solver_index + 1) % len(solver_options)
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS): depth = min(15, depth + 1)
                elif event.key == pygame.K_MINUS: depth = max(1, depth - 1)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE): choosing = False

    return solver_options[solver_index], depth

# ==============================
# MAIN LOOP
# ==============================
def main():
    global tree_zoom, tree_pan_x, tree_pan_y, expanded_nodes_count

    SCREEN_WIDTH = UI["SCREEN_WIDTH"]
    SCREEN_HEIGHT = UI["SCREEN_HEIGHT"]
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Connect 4")

    # Menus
    player_color = draw_color_menu(screen, SCREEN_WIDTH, SCREEN_HEIGHT)
    ai_color = YELLOW if player_color == RED else RED
    rows, cols = draw_board_size_menu(screen, SCREEN_WIDTH, SCREEN_HEIGHT)
    SELECTED_SOLVER, SEARCH_DEPTH = draw_ai_settings_menu(screen, SCREEN_WIDTH, SCREEN_HEIGHT)

    # Layout rects
    left_ratio = UI["LEFT_RATIO"]
    OUTER = UI["OUTER_MARGIN"]
    BOARD_TOP = UI["BOARD_TOP_PAD"]
    BOARD_BOTTOM = UI["BOARD_BOTTOM_PAD"]
    PANEL_PAD = UI["PANEL_SIDE_PAD"]
    INNER = UI["PANEL_INNER_PAD"]

    # area in which the board is visible on the left
    BOARD_AREA = pygame.Rect(
        OUTER,
        BOARD_TOP,
        int(SCREEN_WIDTH * left_ratio) - 2 * OUTER,
        SCREEN_HEIGHT - BOARD_TOP - BOARD_BOTTOM,
    )
    # area in which the other options are visible on the right
    PANEL_AREA = pygame.Rect(
        int(SCREEN_WIDTH * left_ratio) + PANEL_PAD,
        OUTER,
        int(SCREEN_WIDTH * (1 - left_ratio)) - (PANEL_PAD + OUTER),
        SCREEN_HEIGHT - 2 * OUTER,
    )
    # tree viewport
    tree_rect = pygame.Rect(
        PANEL_AREA.left + INNER,
        PANEL_AREA.top + UI["TREE_TOP_GAP"],
        PANEL_AREA.width - 2 * INNER,
        PANEL_AREA.height - UI["TREE_TOP_GAP"] - UI["TREE_BOTTOM_GAP"],
    )
    # game fonts 
    myfont = pygame.font.SysFont("monospace", UI["FONT_MAIN"], bold=True)
    small_font = pygame.font.SysFont("monospace", UI["FONT_SMALL"])
    ai_font = pygame.font.SysFont("monospace", max(16, UI["FONT_TREE"]))

    # game board
    board = BitBoard(rows, cols)
    global WINDOW_MASKS
    WINDOW_MASKS = None

    # game state
    turn = random.randint(PLAYER, AI)            # choose which player starts randomly 
    game_over = False
    player_score = 0
    ai_score = 0
    hover_col = None
    move_start_time = time.time()

    # undo
    history = []

    # tree state
    current_tree_root = None
    dragging = False
    drag_last = (0, 0)
    # converts mouse x-coordinate to board column.
    def column_from_mouse(x):
        sq, offset_x, _ = compute_grid_geom(BOARD_AREA, rows, cols)
        if x < offset_x or x >= offset_x + cols * sq:
            return None
        return (x - offset_x) // sq
    # add the play to history
    def push_history():
        history.append((board.copy(), turn, player_score, ai_score))
    # reverses the players move to until reaching his previous turn
    def pop_history_once():
        nonlocal board, turn, player_score, ai_score, game_over, current_tree_root
        if history:
            board, turn, player_score, ai_score = history.pop()
            game_over = False
            current_tree_root = None

    def undo_to_player_turn():
        if not history: return
        pop_history_once()
        while history and turn != PLAYER:
            pop_history_once()
    # resets the whole game
    def restart_game():
        nonlocal board, turn, player_score, ai_score, game_over, history, current_tree_root, move_start_time, hover_col
        board = BitBoard(rows, cols)
        global WINDOW_MASKS
        WINDOW_MASKS = None
        turn = random.randint(PLAYER, AI)
        player_score = 0
        ai_score = 0
        game_over = False
        history = []
        current_tree_root = None
        tree_zoom, tree_pan_x, tree_pan_y = 1.0, 0, 0
        move_start_time = time.time()
        hover_col = None

    # MAIN LOOP
    clock = pygame.time.Clock()
    while True:
        screen.fill(BLACK)
        # board
        draw_board(screen, board, BOARD_AREA, player_color, ai_color)       # draws score and hover preview disc
        if hover_col is not None:
            sq, offset_x, offset_y = compute_grid_geom(BOARD_AREA, rows, cols)
            cx = offset_x + hover_col * sq + sq // 2
            cy = offset_y - 25
            pygame.draw.circle(screen, player_color, (cx, cy), int(sq * UI["HOVER_DISC_RATIO"]))

        score_text = small_font.render(f"Score  P:{player_score}  AI:{ai_score}", True, WHITE)
        screen.blit(score_text, (BOARD_AREA.left, max(OUTER, BOARD_AREA.top - 42)))

        # right panel
        elapsed = int(time.time() - move_start_time)
        icon_rects = draw_player_panel(screen, PANEL_AREA, turn, player_color, ai_color, elapsed, myfont, UI)

        tree_hdr = small_font.render("Search Tree", True, MUTED)
        screen.blit(tree_hdr, (tree_rect.left, tree_rect.top - 26))
        pygame.draw.rect(screen, (8, 8, 8), tree_rect, border_radius=UI["TREE_BORDER_RADIUS"])
        pygame.draw.rect(screen, (55, 55, 55), tree_rect, 1, border_radius=UI["TREE_BORDER_RADIUS"])

        # draw tree directly into viewport 
        if current_tree_root is not None:
            _draw_tree_viewport(screen, tree_rect, current_tree_root,
                                ai_font, UI["TREE_X_SPACING"], UI["TREE_Y_SPACING"], UI["TREE_MAX_LEVEL"])

        # overlay
        if game_over:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            msg_font = pygame.font.SysFont("monospace", 32, bold=True)
            msg = msg_font.render("Game Over – ESC: exit  •  R: restart", True, (240, 240, 240))
            overlay.blit(msg, (SCREEN_WIDTH // 2 - msg.get_width() // 2, 30))
            screen.blit(overlay, (0, 0))

        pygame.display.update()
        clock.tick(60)

        # events
        mods = pygame.key.get_mods()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: pygame.quit(); sys.exit()
                if event.key == pygame.K_s:            # Changes the solver type mid-game
                    solvers = ["Minimax", "Alpha-Beta", "Expected Minimax"]
                    idx = solvers.index(SELECTED_SOLVER)
                    SELECTED_SOLVER = solvers[(idx + 1) % len(solvers)]
                elif event.key == pygame.K_u: undo_to_player_turn()     # clicking U undo to last player turn
                elif event.key == pygame.K_r: restart_game()            # clicking R restarts the game
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    mx, my = tree_rect.center;  # zoom at center
                    # zoom in
                    lx = mx - tree_rect.left; ly = my - tree_rect.top
                    if tree_zoom != 0:
                        wx = (lx - tree_pan_x) / tree_zoom
                        wy = (ly - tree_pan_y) / tree_zoom
                        new_zoom = max(UI["ZOOM_MIN"], min(UI["ZOOM_MAX"], tree_zoom * (1.0 + UI["ZOOM_STEP"])))
                        tree_pan_x = lx - wx * new_zoom
                        tree_pan_y = ly - wy * new_zoom
                        tree_zoom = new_zoom
                elif event.key == pygame.K_MINUS:         # zoom out 
                    mx, my = tree_rect.center
                    lx = mx - tree_rect.left; ly = my - tree_rect.top
                    if tree_zoom != 0:
                        wx = (lx - tree_pan_x) / tree_zoom
                        wy = (ly - tree_pan_y) / tree_zoom
                        new_zoom = max(UI["ZOOM_MIN"], min(UI["ZOOM_MAX"], tree_zoom * (1.0 - UI["ZOOM_STEP"])))
                        tree_pan_x = lx - wx * new_zoom
                        tree_pan_y = ly - wy * new_zoom
                        tree_zoom = new_zoom
                elif event.key == pygame.K_0:
                    tree_zoom, tree_pan_x, tree_pan_y = 1.0, 0, 0
                elif event.key == pygame.K_LEFT:  tree_pan_x += UI["PAN_STEP"]
                elif event.key == pygame.K_RIGHT: tree_pan_x -= UI["PAN_STEP"]
                elif event.key == pygame.K_UP:    tree_pan_y += UI["PAN_STEP"]
                elif event.key == pygame.K_DOWN:  tree_pan_y -= UI["PAN_STEP"]

            if event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if tree_rect.collidepoint(mx, my) and current_tree_root is not None:
                    ctrl = mods & pygame.KMOD_CTRL
                    shift = mods & pygame.KMOD_SHIFT
                    if ctrl:
                        # zoom at cursor
                        lx = mx - tree_rect.left; ly = my - tree_rect.top
                        if tree_zoom != 0:
                            wx = (lx - tree_pan_x) / tree_zoom
                            wy = (ly - tree_pan_y) / tree_zoom
                            new_zoom = max(UI["ZOOM_MIN"], min(UI["ZOOM_MAX"], tree_zoom * (1.0 + UI["ZOOM_STEP"]*event.y)))
                            tree_pan_x = lx - wx * new_zoom
                            tree_pan_y = ly - wy * new_zoom
                            tree_zoom = new_zoom
                    else:
                        if shift: tree_pan_x += event.y * UI["PAN_STEP"]
                        else:     tree_pan_y += event.y * UI["PAN_STEP"]

            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button in (2, 3) and tree_rect.collidepoint(event.pos):
                    dragging = True; drag_last = event.pos

                # expand/collapse by clicking nodes (anchor under cursor)
                if event.button == 1 and tree_rect.collidepoint(event.pos) and current_tree_root is not None:
                    wx, wy = screen_to_world(tree_rect, *event.pos)
                    clicked = None
                    for node, rect in reversed(_tree_hitboxes_world):
                        if rect.collidepoint(wx, wy):
                            clicked = node; break
                    if clicked is not None:
                        lx = event.pos[0] - tree_rect.left
                        ly = event.pos[1] - tree_rect.top
                        clicked.expanded = not getattr(clicked, "expanded", True)
                        # re-layout and keep the clicked node under the cursor
                        _pos, _ = _layout_tree_world(current_tree_root, UI["TREE_X_SPACING"], UI["TREE_Y_SPACING"], UI["TREE_MAX_LEVEL"])
                        if id(clicked) in _pos:
                            cx, cy = _pos[id(clicked)]
                            tree_pan_x = lx - cx * tree_zoom
                            tree_pan_y = ly - cy * tree_zoom

                # icons
                if event.button == 1:
                    for label, r in icon_rects:
                        if r.collidepoint(event.pos):
                            if label == "EXIT":
                                pygame.quit(); sys.exit()
                            elif label == "UNDO":
                                undo_to_player_turn()
                            elif label == "RESTART":
                                restart_game()

                # player move 
                if event.button == 1 and turn == PLAYER and not game_over and not tree_rect.collidepoint(event.pos):
                    col = column_from_mouse(event.pos[0])
                    if col is not None and board.is_valid_location(col):
                        push_history()
                        # in case of expecti-minimax we add a probability for a wrong drop for the player also
                        if SELECTED_SOLVER == "Expected Minimax": 
                            col = probabilistic_drop(board.copy(), col, PLAYER_PIECE) if col is not None else None
                        board.drop_piece(col, PLAYER_PIECE)     # drop piece 
                        player_score = count_connect_fours(board, PLAYER_PIECE)    # update overall score
                        ai_score = count_connect_fours(board, AI_PIECE)
                        draw_board(screen, board, BOARD_AREA, player_color, ai_color)
                        pygame.display.update()
                        turn = AI              # switch turns
                        move_start_time = time.time()
                        hover_col = None
                        current_tree_root = None  # new tree next AI turn
                        tree_zoom, tree_pan_x, tree_pan_y = 1.0, 0, 0

            if event.type == pygame.MOUSEBUTTONUP:
                if event.button in (2, 3): dragging = False

            if event.type == pygame.MOUSEMOTION:
                if dragging and current_tree_root is not None:
                    mx, my = event.pos; lx, ly = drag_last
                    tree_pan_x += (mx - lx); tree_pan_y += (my - ly)
                    drag_last = (mx, my)
                elif turn == PLAYER:
                    col = column_from_mouse(event.pos[0]); hover_col = col

        # AI move
        if turn == AI and not game_over:
            valid_locations = board.get_valid_locations()
            if not valid_locations:
                game_over = True
            else:
                start_time = time.time()
                try:
                    if SELECTED_SOLVER == "Alpha-Beta":
                        root, value = minimax_alpha_beta_tree(board, SEARCH_DEPTH, -math.inf, math.inf, True)
                        actual_col = root.col
                    elif SELECTED_SOLVER == "Expected Minimax":
                        root, value = expected_minimax_tree(board, SEARCH_DEPTH, True)
                        actual_col = probabilistic_drop(board.copy(), root.col, AI_PIECE) if root.col is not None else None
                    else:
                        root, value = minimax_tree(board, SEARCH_DEPTH, True)
                        actual_col = root.col
                except Exception as e:
                    print("AI error:", repr(e))
                    root = Node(board.copy(), score=score_position(board, AI_PIECE), node_type="terminal")
                    value = 0; actual_col = None

                current_tree_root = root
                init_tree_expansion(current_tree_root, max_open_depth=1)

                elapsed_search = time.time() - start_time       # time taken to solve
                print(f"[{SELECTED_SOLVER}] AI chose column {root.col + 1} value={value:.3f} in {elapsed_search:.3f}s nodes expanded:{expanded_nodes_count} ")
                expanded_nodes_count = 0        # reset expanded nodes for each ply
                if actual_col is None or not board.is_valid_location(actual_col):
                    v = board.get_valid_locations()
                    if v:
                        actual_col = sorted(v, key=lambda c: abs(c - board.cols // 2))[0]

                if actual_col is not None and board.is_valid_location(actual_col):
                    push_history()
                    pygame.time.wait(350)
                    board.drop_piece(actual_col, AI_PIECE)  # make move
                    player_score = count_connect_fours(board, PLAYER_PIECE)     # update overall score
                    ai_score = count_connect_fours(board, AI_PIECE)
                    turn = PLAYER    # switch turn
                    move_start_time = time.time()

        if is_terminal_node(board):
            game_over = True

if __name__ == "__main__":
    main()
