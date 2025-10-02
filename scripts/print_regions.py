import os
from Actions import Actions


def main():
    acts = Actions()
    print("Window:")
    print(f"  LEFT={acts.WIN_LEFT} TOP={acts.WIN_TOP} WIDTH={acts.WIN_WIDTH} HEIGHT={acts.WIN_HEIGHT}")
    print("Field:")
    print(f"  TL=({acts.TOP_LEFT_X},{acts.TOP_LEFT_Y}) BR=({acts.BOTTOM_RIGHT_X},{acts.BOTTOM_RIGHT_Y})")
    print("Card bar:")
    print(f"  X={acts.CARD_BAR_X} Y={acts.CARD_BAR_Y} W={acts.CARD_BAR_WIDTH} H={acts.CARD_BAR_HEIGHT}")

    os.makedirs("screenshots", exist_ok=True)
    acts.capture_area(os.path.join("screenshots", "field_region.png"))
    acts.capture_card_area(os.path.join("screenshots", "cardbar_region.png"))
    print("Saved screenshots/field_region.png and screenshots/cardbar_region.png")


if __name__ == "__main__":
    main()
