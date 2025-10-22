import numpy as np
import cv2




class SelectRectange():
    def __init__(self, image: np.ndarray = None):
        self.image_size = (640,480)

        if image is not None:
            self.canvas = image.copy()
        else:
            self.canvas = np.zeros((self.image_size[0],self.image_size[1],3), dtype=np.uint8)

        self.color = (255, 0, 0)    # BGR
        
        self.window_name = "Select an rect by LMP x2, q - quit"
        self.points = []


    def callback_pick_rectangle(self, event, x, y, flags, img):
        if event == cv2.EVENT_LBUTTONDOWN and len(self.points) < 2:
            self.points.append((int(x),int(y)))
            cv2.circle(img, (x,y), 1, (0,255,255), -1)


    def select_and_get_rect(self,
                            new_image : np.ndarray = None             
                            ):
        
        if new_image is not None:
            self.canvas = new_image.copy()
            self.points = []

        temp = self.canvas.copy()
        
        cv2.namedWindow(self.window_name)
        cv2.imshow(self.window_name, self.canvas)
        cv2.setMouseCallback(self.window_name , self.callback_pick_rectangle, self.canvas)

        while True:
            if len(self.points) >= 2:
                break

            cv2.imshow(self.window_name, self.canvas)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                return None, None

        cv2.destroyAllWindows()

        x1, y1 = self.points[0]
        x2, y2 = self.points[1]

        x = min(x1, x2)
        y = min(y1, y2)
        w = abs(x1 - x2)
        h = abs(y1 - y2)

        rect_bb = (x, y, w, h)
        rect_img = temp[y:y+h, x:x+w]

        return rect_bb, rect_img









class SelectArea():
    def __init__(self, image: np.ndarray = None):
        self.image_size = (640,480)

        if image is not None:
            self.canvas = image.copy()
        else:
            self.canvas = np.zeros((self.image_size[0],self.image_size[1],3), dtype=np.uint8)

        self.color = (255, 0, 0)    # BGR
        
        self.window_name = "Select an object, f - finish, q - quit"
        self.drawing = False
        self.points = []


    def draw_by_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            if len(self.points) > 1:
                self.canvas = np.zeros((self.image_size[0],self.image_size[1],3), dtype=np.uint8)
                self.points = []
            self.points = [(x, y)]
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.points.append((x, y))
            cv2.circle(self.canvas, (x, y), 1, self.color, -1)
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            

    def draw_and_get_area(self,
                          new_image : np.ndarray = None,
                          print_info : bool = False,
                          show_result: bool = False,                          
                          ) -> np.ndarray:
        
        if new_image is not None:
            self.canvas = new_image.copy()

        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self.draw_by_mouse)
    
        if print_info:
            print('LMP for draw')
            print('f for finish draw')
            print('q for quit')
    
        while True:
            cv2.imshow(self.window_name, self.canvas)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                cv2.destroyAllWindows()
                return None
            
            elif key == ord('f'):
                if print_info:
                    print('FINISH')

                if len(self.points) > 2:
                    pts = np.array(self.points, np.int32)
                    pts = pts.reshape((-1, 1, 2))
                    cv2.fillPoly(self.canvas, [pts], self.color)

                    if show_result:
                        cv2.imshow(self.window_name, self.canvas)
                        cv2.waitKey(0)
                    cv2.destroyAllWindows()
                    
                    mask = np.zeros(self.canvas.shape[:2], dtype=np.uint8) 
                    mask[np.all(self.canvas == self.color, axis=-1)] = 255
                    return mask



