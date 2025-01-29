import pygame
import numpy as np
import serial
import time
import math

# Configuration du port série
SERIAL_PORT = "COM11"
BAUD_RATE = 19200

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
except Exception as e:
    print(f"Erreur lors de l'ouverture du port série : {e}")
    ser = None

# Constants
MATRIX_SIZE = 8
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
LED_BASE_SIZE = 20
LED_BASE_SPACING = 30
GRID_OFFSET_X = WINDOW_WIDTH // 2
GRID_OFFSET_Y = WINDOW_HEIGHT // 3

# Couleurs
BACKGROUND = (200, 200, 200)
LED_OFF = (0, 0, 0)
LED_ON = (255, 0, 0)
SLIDER_BG = (150, 150, 150)
SLIDER_FG = (100, 100, 100)
TEXT_COLOR = (50, 50, 50)


class Slider:
    def __init__(self, x, y, width, height, min_val, max_val, initial_val, label):
        self.rect = pygame.Rect(x, y, width, height)
        self.min_val = min_val
        self.max_val = max_val
        self.value = initial_val
        self.grabbed = False
        self.label = label

    def draw(self, surface, font):
        pygame.draw.rect(surface, SLIDER_BG, self.rect)
        pos = (
            self.rect.x
            + (self.value - self.min_val)
            / (self.max_val - self.min_val)
            * self.rect.width
        )
        cursor_rect = pygame.Rect(pos - 5, self.rect.y - 5, 10, self.rect.height + 10)
        pygame.draw.rect(surface, SLIDER_FG, cursor_rect)

        label_text = font.render(f"{self.label}: {self.value:.1f}", True, TEXT_COLOR)
        surface.blit(label_text, (self.rect.x, self.rect.y - 20))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.grabbed = True
        elif event.type == pygame.MOUSEBUTTONUP:
            self.grabbed = False
        elif event.type == pygame.MOUSEMOTION and self.grabbed:
            rel_x = max(0, min(event.pos[0] - self.rect.x, self.rect.width))
            self.value = self.min_val + (rel_x / self.rect.width) * (
                self.max_val - self.min_val
            )
            return True
        return False


class LEDMatrix:
    def __init__(self):
        self.matrix = np.zeros((MATRIX_SIZE, MATRIX_SIZE, MATRIX_SIZE), dtype=int)
        self.rotation_x = 30
        self.rotation_y = 45
        self.led_size = LED_BASE_SIZE
        self.led_spacing = LED_BASE_SPACING
        self.last_toggled = None  # Stocke la dernière LED togglée

        # Points centraux des faces (x, y, z)
        self.face_centers = {
            "H": (3.5, 0, 3.5),  # Haut
            "B": (3.5, 7, 3.5),  # Bas
            "G": (0, 3.5, 3.5),  # Gauche
            "D": (7, 3.5, 3.5),  # Droite
            "F": (3.5, 3.5, 0),  # Face (devant)
            "A": (3.5, 3.5, 7),  # Arrière
        }

    def rotate_point(self, x, y, z):
        # Centre les coordonnées
        x -= (MATRIX_SIZE - 1) / 2
        y -= (MATRIX_SIZE - 1) / 2
        z -= (MATRIX_SIZE - 1) / 2

        # Rotation autour de l'axe Y (inversée)
        angle_y = math.radians(-self.rotation_y)
        x_rot = x * math.cos(angle_y) - z * math.sin(angle_y)
        z_rot = x * math.sin(angle_y) + z * math.cos(angle_y)

        # Rotation autour de l'axe X (inversée)
        angle_x = math.radians(-self.rotation_x)
        y_final = y * math.cos(angle_x) - z_rot * math.sin(angle_x)
        z_final = y * math.sin(angle_x) + z_rot * math.cos(angle_x)

        # Projection isométrique
        scale = 1
        screen_x = GRID_OFFSET_X + (x_rot * self.led_spacing) * scale
        screen_y = GRID_OFFSET_Y + (y_final * self.led_spacing) * scale

        return int(screen_x), int(screen_y), z_final

    def screen_to_matrix(self, screen_x, screen_y):
        closest_dist = float("inf")
        closest_point = None

        for x in range(MATRIX_SIZE):
            for y in range(MATRIX_SIZE):
                for z in range(MATRIX_SIZE):
                    sx, sy, _ = self.rotate_point(x, y, z)
                    dist = (sx - screen_x) ** 2 + (sy - screen_y) ** 2
                    if dist < closest_dist:
                        closest_dist = dist
                        closest_point = (x, y, z)

        if closest_dist < (self.led_size * 2) ** 2:
            return closest_point
        return None

    def toggle_led(self, x, y, z):
        self.matrix[x, y, z] ^= 1
        # Mémorise la dernière LED togglée
        self.last_toggled = (x, y, z)
        self.send_frame()

    def send_frame(self):
        if ser:
            try:
                ser.write(bytes([0xF2]))
                # Boucle sur le "nouveau" Z (qui correspond à l'ancien X)
                for newZ in range(MATRIX_SIZE):
                    for y in range(MATRIX_SIZE):
                        y_inversé = MATRIX_SIZE - 1 - y  # Inversion de l'axe Y
                        val = 0
                        # Boucle sur le "nouveau" X (qui correspond à l'ancien Z)
                        for newX in range(MATRIX_SIZE):
                            oldX = newZ
                            oldZ = newX
                            if self.matrix[oldX, y_inversé, oldZ]:
                                val |= 1 << newX
                        ser.write(bytes([val]))
            except Exception as e:
                print(f"Erreur lors de l'envoi des données : {e}")

    def draw_face_labels(self, surface, font):
        # Collecter tous les points avec leurs coordonnées écran et profondeur
        face_points = []
        for label, (x, y, z) in self.face_centers.items():
            screen_x, screen_y, depth = self.rotate_point(x, y, z)
            face_points.append((label, screen_x, screen_y, depth))

        # Trier les points par profondeur pour un affichage correct
        face_points.sort(key=lambda p: p[3], reverse=True)

        # Dessiner les labels
        for label, x, y, _ in face_points:
            # Créer un cercle de fond pour le texte
            circle_radius = int(self.led_size * 0.8)
            pygame.draw.circle(surface, BACKGROUND, (x, y), circle_radius)
            pygame.draw.circle(surface, TEXT_COLOR, (x, y), circle_radius, 1)

            # Afficher le texte
            text_surface = font.render(label, True, TEXT_COLOR)
            text_rect = text_surface.get_rect(center=(x, y))
            surface.blit(text_surface, text_rect)

    def draw(self, surface, font):
        # Dessiner les LED
        points = []
        for x in range(MATRIX_SIZE):
            for y in range(MATRIX_SIZE):
                for z in range(MATRIX_SIZE):
                    screen_x, screen_y, depth = self.rotate_point(x, y, z)
                    points.append((x, y, z, screen_x, screen_y, depth))

        # Tri par profondeur pour dessiner correctement
        points.sort(key=lambda p: p[5], reverse=True)

        for x, y, z, screen_x, screen_y, _ in points:
            color = LED_ON if self.matrix[x, y, z] else LED_OFF
            radius = int(self.led_size * 0.4)
            pygame.draw.circle(surface, color, (screen_x, screen_y), radius)
            pygame.draw.circle(surface, (50, 50, 50), (screen_x, screen_y), radius, 1)

        # Dessiner les labels après les LED
        self.draw_face_labels(surface, font)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 24)

    led_matrix = LEDMatrix()

    size_slider = Slider(
        50, WINDOW_HEIGHT - 80, 200, 20, 10, 30, LED_BASE_SIZE, "Taille LED"
    )
    spacing_slider = Slider(
        300, WINDOW_HEIGHT - 80, 200, 20, 20, 50, LED_BASE_SPACING, "Espacement"
    )

    dragging = False
    last_mouse_pos = None

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    mouse_pos = pygame.mouse.get_pos()
                    # Si on clique dans la zone d'affichage LED (hors sliders)
                    if mouse_pos[1] < WINDOW_HEIGHT - 100:
                        matrix_pos = led_matrix.screen_to_matrix(*mouse_pos)
                        if matrix_pos:
                            led_matrix.toggle_led(*matrix_pos)
                elif event.button == 3:
                    dragging = True
                    last_mouse_pos = pygame.mouse.get_pos()

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 3:
                    dragging = False

            elif event.type == pygame.MOUSEMOTION:
                if dragging and last_mouse_pos:
                    dx = event.pos[0] - last_mouse_pos[0]
                    dy = event.pos[1] - last_mouse_pos[1]
                    led_matrix.rotation_y -= dx * 0.5
                    led_matrix.rotation_x -= dy * 0.5
                    last_mouse_pos = event.pos

            # Gestion des sliders
            if size_slider.handle_event(event):
                led_matrix.led_size = size_slider.value
            if spacing_slider.handle_event(event):
                led_matrix.led_spacing = spacing_slider.value

        screen.fill(BACKGROUND)
        led_matrix.draw(screen, font)

        # Affichage en haut à gauche de la dernière LED togglée
        if led_matrix.last_toggled is not None:
            info_text = f"Dernière LED togglée : {led_matrix.last_toggled}"
            text_surface = font.render(info_text, True, TEXT_COLOR)
            screen.blit(text_surface, (10, 10))

        size_slider.draw(screen, font)
        spacing_slider.draw(screen, font)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    if ser:
        ser.close()


if __name__ == "__main__":
    main()
