#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <AsyncTCP.h>
#include <MPU6050_tockn.h>
#include <Wire.h>
#include <ArduinoJson.h>

// WiFi credentials
const char* ssid = "WIFI PT";  
const char* password = "123456789";  

// I2C pins for ESP32-C3
#define I2C_SDA 3
#define I2C_SCL 4

// MPU6050 setup
TwoWire I2C = TwoWire(0);
MPU6050 mpu(I2C);

// Web server
AsyncWebServer server(80);
AsyncWebSocket ws("/ws");

// Variables
bool isRunning = false;
unsigned long lastTime = 0;
const unsigned long SAMPLE_INTERVAL = 50; // 50ms = 20Hz sampling rate

// Data structure
struct SensorData {
  unsigned long timestamp;
  float accelX;
  float accelY;
  float accelZ;
  float gyroX;
  float gyroY;
  float gyroZ;
};

void onWsEvent(AsyncWebSocket *server, AsyncWebSocketClient *client, AwsEventType type, void *arg, uint8_t *data, size_t len) {
  if (type == WS_EVT_CONNECT) {
    Serial.println("Client connected");
    // Send current status
    client->text("{\"status\":\"connected\",\"sampleRate\":" + String(1000/SAMPLE_INTERVAL) + "}");
  } 
  else if (type == WS_EVT_DISCONNECT) {
    Serial.println("Client disconnected");
  } 
  else if (type == WS_EVT_DATA) {
    String message = "";
    for (size_t i = 0; i < len; i++) {
      message += (char)data[i];
    }
    
    if (message == "start") {
      isRunning = true;
      Serial.println("Data collection started");
    } 
    else if (message == "stop") {
      isRunning = false;
      Serial.println("Data collection stopped");
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  // Initialize I2C
  I2C.begin(I2C_SDA, I2C_SCL);
  mpu.begin();
  mpu.calcGyroOffsets();
  Serial.println("MPU6050 initialized");

  // Connect to WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  Serial.println("Connected to WiFi");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // WebSocket setup
  ws.onEvent(onWsEvent);
  server.addHandler(&ws);

  // Simple API endpoint to get current data
  server.on("/data", HTTP_GET, [](AsyncWebServerRequest *request){
    mpu.update();
    
    DynamicJsonDocument doc(200);
    doc["timestamp"] = millis();
    doc["accelX"] = mpu.getAccX() * 9.81; // Convert to m/s²
    doc["accelY"] = mpu.getAccY() * 9.81;
    doc["accelZ"] = mpu.getAccZ() * 9.81;
    doc["gyroX"] = mpu.getGyroX();
    doc["gyroY"] = mpu.getGyroY();
    doc["gyroZ"] = mpu.getGyroZ();
    
    String response;
    serializeJson(doc, response);
    request->send(200, "application/json", response);
  });

  // Status endpoint
  server.on("/status", HTTP_GET, [](AsyncWebServerRequest *request){
    request->send(200, "text/plain", "ESP32 Wave Sensor Ready");
  });

  server.begin();
  Serial.println("HTTP server started");
  Serial.println("WebSocket server started on /ws");
  Serial.println("Ready for data collection!");
}

void loop() {
  if (isRunning && millis() - lastTime >= SAMPLE_INTERVAL) {
    lastTime = millis();
    
    // Update MPU6050
    mpu.update();
    
    // Create JSON data
    DynamicJsonDocument doc(300);
    doc["timestamp"] = millis();
    doc["accelX"] = mpu.getAccX() * 9.81; // m/s²
    doc["accelY"] = mpu.getAccY() * 9.81;
    doc["accelZ"] = mpu.getAccZ() * 9.81;
    doc["gyroX"] = mpu.getGyroX();
    doc["gyroY"] = mpu.getGyroY();
    doc["gyroZ"] = mpu.getGyroZ();
    
    // Send to all connected clients
    String jsonString;
    serializeJson(doc, jsonString);
    ws.textAll(jsonString);
    
    // Also print to Serial for debugging
    Serial.println(jsonString);
  }
  delay(1000);
  // Clean up disconnected clients
  ws.cleanupClients();
}