import chess
import chess.engine
import os # Added to access environment variables

# It's recommended to make stockfish_path configurable,
# for example, via an environment variable.
STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "stockfish")

def describe_quality(loss: int) -> str:
    """
    Describes the quality of a chess move based on centipawn loss.
    """
    if loss < 20:
        return "Excellent"
    if loss < 50:
        return "Good"
    if loss < 100:
        return "Inaccuracy"
    if loss < 300:
        return "Mistake"
    return "Blunder"

def evaluate_llm_move_logic(
    fen: str,
    llm_move_san: str,
    top_n: int = 3,
    multipv: bool = False,
) -> dict:
    """
    Core logic to evaluate an LLM's SAN move using Stockfish.
    (This is your original function, renamed to avoid conflict with the main handler's scope)
    """
    board = chess.Board(fen)
    llm_color = "white" if fen.split()[1] == "w" else "black"

    try:
        llm_move = board.parse_san(llm_move_san)
    except ValueError:
        return {
            "llm_move": llm_move_san,
            "llm_eval": 10000,
            "centipawn_loss": 10000,
            "move_quality": 'Illegal',
            "llm_color": llm_color,
            "error": "Illegal move format or invalid move."
        }

    llm_move_uci = llm_move.uci()

    try:
        # Ensure Stockfish path is correctly set for the serverless environment
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            # Get top N Stockfish moves from original position
            analysis_result = engine.analyse(board, chess.engine.Limit(time=0.1), multipv=top_n)
            
            if multipv and top_n > 1 and isinstance(analysis_result, list):
                stockfish_top_moves = [info['pv'][0].uci() for info in analysis_result]
                stockfish_best_score = analysis_result[0]['score'].relative.score()
            elif isinstance(analysis_result, list) and analysis_result: # Check if list and not empty
                top_info = analysis_result[0]
                stockfish_top_moves = [top_info['pv'][0].uci()]
                stockfish_best_score = top_info['score'].relative.score()
            elif not isinstance(analysis_result, list): # Single PV result
                stockfish_top_moves = [analysis_result['pv'][0].uci()]
                stockfish_best_score = analysis_result['score'].relative.score()
            else: # Fallback if analysis_result is empty or unexpected
                 return {
                    "error": "Stockfish analysis returned unexpected result format.",
                    "llm_color": llm_color,
                }


            # Apply LLM move and evaluate
            board.push(llm_move)
            post_move_fen = board.fen()
            llm_result = engine.analyse(board, chess.engine.Limit(time=0.1))
            llm_score = llm_result['score'].relative.score()
            board.pop() # Important to pop the move to revert board state

    except chess.engine.EngineTerminatedError:
        return {
            "error": "Stockfish engine terminated unexpectedly. Check path and permissions.",
            "llm_color": llm_color,
        }
    except Exception as e:
        return {
            "error": f"An error occurred during Stockfish analysis: {str(e)}",
            "llm_color": llm_color,
        }

    # Compute centipawn loss from LLM's POV
    if llm_color == "white":
        centipawn_loss = stockfish_best_score - llm_score
    else:
        centipawn_loss = llm_score - stockfish_best_score

    move_quality = describe_quality(centipawn_loss)

    return {
        "stockfish_moves": stockfish_top_moves,
        "stockfish_eval": stockfish_best_score,
        "llm_move": llm_move_uci,
        "post_move_fen": post_move_fen,
        "llm_eval": llm_score,
        "centipawn_loss": centipawn_loss,
        "move_quality": move_quality,
        "llm_color": llm_color,
    }

def main(event: dict, context=None) -> dict:
    """
    DigitalOcean Serverless Function handler.
    The 'event' dictionary will contain the input parameters.
    """
    # Extract parameters from the event dictionary
    # It's good practice to provide defaults or handle missing parameters
    fen = event.get("fen")
    llm_move_san = event.get("llm_move_san")
    top_n = event.get("top_n", 3)
    multipv = event.get("multipv", False)

    if not fen or not llm_move_san:
        return {
            "statusCode": 400, # Bad Request
            "body": {
                "error": "Missing required parameters: 'fen' and 'llm_move_san' must be provided."
            }
        }

    # Call your core logic function
    result = evaluate_llm_move_logic(fen, llm_move_san, top_n, multipv)

    # The function should return a dictionary, which will be serialized to JSON.
    # If an error occurred in evaluate_llm_move_logic, it will be in the result.
    if "error" in result:
         return {
            "statusCode": 500, # Internal Server Error (or a more specific error if applicable)
            "body": result
         }

    return {
        "statusCode": 200, # OK
        "body": result
    }