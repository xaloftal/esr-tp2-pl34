syntax = "proto3";

package control_protocol;

// Mensagem principal de controlo
message ControlMessage {
  enum MessageType {
    UNKNOWN = 0;
    REGISTER = 1;            // Nó -> Bootstrapper
    REGISTER_RESPONSE = 2;   // Bootstrapper -> Nó
    HELLO = 3;               // Nó -> Nó
  }

  MessageType type = 1;  // Tipo da mensagem
  string node_id = 2;    // Identificador do nó
  string node_ip = 3;    // Endereço IP
  int32 control_port = 4;// Porta TCP para controlo
  int32 data_port = 5;   // (Reservada p/ Etapa 4)
  repeated Neighbor neighbors = 6;  // Lista de vizinhos (em respostas)
}

// Estrutura que representa um vizinho
message Neighbor {
  string node_id = 1;
  string node_ip = 2;
  int32 control_port = 3;
  int32 data_port = 4;
}
