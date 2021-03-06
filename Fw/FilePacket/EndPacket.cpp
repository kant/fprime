// ====================================================================== 
// \title  EndPacket.cpp
// \author bocchino
// \brief  cpp file for FilePacket::EndPacket
//
// \copyright
// Copyright 2009-2016, by the California Institute of Technology.
// ALL RIGHTS RESERVED.  United States Government Sponsorship
// acknowledged. Any commercial use must be negotiated with the Office
// of Technology Transfer at the California Institute of Technology.
// 
// This software may be subject to U.S. export control laws and
// regulations.  By accepting this document, the user agrees to comply
// with all U.S. export laws and regulations.  User has the
// responsibility to obtain export licenses, or other export authority
// as may be required before exporting such information to foreign
// countries or providing access to foreign persons.
// ====================================================================== 

#include <string.h>

#include <Fw/FilePacket/FilePacket.hpp>
#include <Fw/Types/Assert.hpp>

namespace Fw {

  void FilePacket::EndPacket ::
    initialize(
        const U32 sequenceIndex,
        const CFDP::Checksum& checksum
    )
  {
    this->header.initialize(FilePacket::T_END, sequenceIndex);
    this->setChecksum(checksum);
  }

  U32 FilePacket::EndPacket ::
    bufferSize(void) const
  {
    return this->header.bufferSize() + sizeof(this->checksumValue);
  }

  SerializeStatus FilePacket::EndPacket ::
    toBuffer(Buffer& buffer) const
  {
    SerialBuffer serialBuffer(
        reinterpret_cast<U8*>(buffer.getdata()),
        buffer.getsize()
    );
    return this->toSerialBuffer(serialBuffer);
  }

  void FilePacket::EndPacket ::
    setChecksum(const CFDP::Checksum& checksum)
  {
    this->checksumValue = checksum.getValue();
  }


  void FilePacket::EndPacket ::
    getChecksum(CFDP::Checksum& checksum) const
  {
    CFDP::Checksum c(this->checksumValue);
    checksum = c;
  }

  SerializeStatus FilePacket::EndPacket ::
    fromSerialBuffer(SerialBuffer& serialBuffer) 
  {

    FW_ASSERT(this->header.type == T_END);

    const SerializeStatus status = 
      serialBuffer.deserialize(this->checksumValue);

    return status;

  }

  SerializeStatus FilePacket::EndPacket ::
    toSerialBuffer(SerialBuffer& serialBuffer) const
  {

    FW_ASSERT(this->header.type == T_END);

    SerializeStatus status;

    status = this->header.toSerialBuffer(serialBuffer);
    if (status != FW_SERIALIZE_OK)
      return status;

    status = serialBuffer.serialize(this->checksumValue);
    if (status != FW_SERIALIZE_OK)
      return status;

    return FW_SERIALIZE_OK;

  }

}
